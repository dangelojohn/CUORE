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

**2026-10-20, morning:** a data snapshot of the car's state and logs is copied into `data/captures/` ([[Data Captured|Data-Captured]]), then **38 simulation logs are removed from it**; four MES files from that morning are examined and found to be simulations; the README and a features list are rewritten; the ESIM bench-test sheet is written; the first version of this wiki is assembled.

**2026-10-20, later the same day:**
- Two reviews of public GitHub projects (Giorgio CAN data; OBD and UDS tooling) are written and filed under licence rules in `external/`, with a ten-point implementation review ([[External References and Licences|External-References-and-Licences]]).
- Four of those points are built, bench-tested only: drain-before-send with a stale-reply audit, an opt-in adapter hard reset, the 11-bit reply-offset and identity-probe addressing pass, and the **listen-only chassis decoder** ([[Passive Chassis Decoding|Passive-Chassis-Decoding]]). A safety fix follows: the 11-bit sweep never transmits on ids the car broadcasts, and leaving a physical target restores default flow control ([[Safety Rules|Safety-Rules]]).
- ESIM knowledge enters the application: a design block with sources (and the "pump" wording corrected), electrical check values, fault-tree steps E9 (orientation) and E10 (back-probe), and mechanic steps for ESIM hypotheses ([[ESIM Bench Test|ESIM-Bench-Test]]).
- **Every non-EVAP code is reviewed**: a network-pattern readings note and a literature note, a full per-system inventory with a camera and driver-assistance deep review, and a body, infotainment, keyless and steering review. Twenty-two code texts are added and U1713 is corrected to "signal erratic". The brake code C104B-92 is recorded as service-induced on the owner's statement, pending a confirming ABS read ([[Code Reviews|Code-Reviews]], [[Network and Brake Findings|Network-and-Brake-Findings]]).
- The findings enter the app as a per-code panel; job selection prefers a job with a SAFETY hypothesis; the vehicle page lists all open jobs (now two) ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]).
- The catalogue's recalls and notices are summarised, with 19V551, 18V205, 25V586 and the engine reflashes (18V636, W05) highlighted for VIN checks ([[Recalls and Campaigns|Recalls-and-Campaigns]]).

**2026-10-22:**
- **ESIM replaced** on the reference car (owner-attested): a new ESIM with a new gasket, mounted white cylinder up where the previous one was down. The EVAP job's ESIM hypothesis becomes "supported", not proven; the proof is a completed EVAP monitor with no code clearing ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]], [[ESIM Bench Test|ESIM-Bench-Test]]).
- **Export bundle** (`cuore.bundle/1.0`, commit `29b8c13`): a `.cuore.zip` of a scan or job, an "Export for AlfaCore" button and `/api/export` routes, with the integration specs written in `docs/integration/` ([[AlfaCore Integration|AlfaCore-Integration]]).
- **`alfa_core_cuore` installed** on the live AlfaCore (tested on a throwaway database, backed up, then installed). The dealer recall request list of 2026-10-20 is filed with the car's PDFs ([[Recalls and Campaigns|Recalls-and-Campaigns]]).- **Owner plans recorded** (owner-attested, not readings): the **rear brake pads** are to be replaced on 2026-10-23 (rotors look and feel good to the owner; no measurements on record), and the car goes to the dealer on **2026-10-28** for the fuel pump recall and to have the engine and transmission mounts inspected. The recall is **93C = NHTSA 25V586000**: FCA's own number for the same campaign. A catalogue row that had called 93C an analogue was wrong and was removed ([[Recalls and Campaigns|Recalls-and-Campaigns]]). The fuel delivery module's lock ring and seal are part of the EVAP sealed system (an inference), so the EVAP proof run is protected: no ECM clear and no battery disconnect without a note.
- **Accessory belt job recorded** (owner-attested, not a reading): a new accessory (serpentine) belt is on site and ready to fit, install date not stated (likely with the rear pads). The owner sees and hears no reason to replace the tensioner or idler/pulley wheels. The job lists general-practice checks to do with the belt off (spin each pulley and the tensioner by hand, tensioner return, alignment and grooves, every rib seated), labelled as external reference.
- **Oil change job recorded** (job `6d55b2e32b2a`, owner-attested, not a reading): an oil and filter change is planned for 2026-10-23, the same day as the rear pads and probably the belt. The job carries the spec from CUORE's own service data (0W-30 full synthetic, FCA/Mopar MS-13340 / API SN; 5.5 US qt with filter; Mopar filter 4892339; drain plug 20 Nm; filter cap 25 Nm; most single-source, gasket/O-ring parts not in CUORE), the MES reset route, a history note on the 2026-09-15 MES oil-change reset (two ECM adjustments logged COMPLETED, no odometer, so it does not show an oil change was actually done), a question to the owner for the last real oil change date and mileage, and the rule not to use any clear-DTC function while the EVAP proof is pending.

**2026-10-23:**
- **First scan after the ESIM replacement** (scan SCAN_2610230010, 00:10, no clearing): EVAP proof INCOMPLETE, Mode 06 0x3A/0x87 at 496 ms against a minimum of 3707, P0440/P0455/P0456 pending and P0440/P0456 permanent, BCM U1711/U1712/U1713 absent since the clear; raw capture, AlfaCore bundle and dealer sheet section E filed ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]).
- **MES backup audit (2025-10 turbo-replacement era):** the 2026-09-13 backup of 97 MES logs held no log the corpus lacked; the October 2025 Stelvio sessions after the owner-attested 2025-10-14 turbo job are simulation-mode, so the genuine record of that era is three ECM-only logs ([docs/research/MES_LOGS_2025-10_TURBO_ERA.md](https://github.com/dangelojohn/CUORE/blob/main/docs/research/MES_LOGS_2025-10_TURBO_ERA.md)).

## Themes that run through the history

1. **The evidence rule grew from experience.** Each correction (three smoke tests rather than two; a Giulia-only bulletin; a "pass" that was a reset value) led to a rule that data, not assertion, carries conclusions.
2. **Tool faults are reported as tool faults.** Silent buses, NO DATA and timing bugs became first-class statuses instead of "nothing wrong".
3. **Safety moved from policy to code.** The incident turned a habit into enforced rules: one rate per bus, one door to the adapter, one audit trail; and later, no request on an id the car itself broadcasts.
4. **Marque data is kept out of code,** so the port to other brands is a data task.
5. **Outside facts are leads.** Public projects, bulletins and forum posts are kept under licence rules and labelled, and a conclusion cites a reading from the car.

Related: [[Roadmap]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
