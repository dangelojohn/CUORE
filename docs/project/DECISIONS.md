# Decisions

Dated architecture and product decisions, newest groups last. Each entry: date, decision, why, commit (where one is known). Dates for commits are git author dates; where a decision was taken in conversation before the commit, the commit is the first that shows it.

## Foundations (2026-08 to 2026-09)

**2026-08-27 - Build on MES's file outputs plus the ELM-class adapter; rebuild the log bridge as a structured library.**
MES (MultiEcuScan) has no API, so everything rides on its log files and the adapter. The log reader became a structured library (`mes`) with typed results instead of text scraping. Commit eca5d08. The OBD-II readiness monitors were the biggest MES gap and were closed the same day (11de50c).

**2026-09-02 - CUORE is a FastAPI companion service over the `mes` library; the earlier Flask web-ui is removed.**
The Flask app covered 6 of 28 tools with no JSON API. CUORE offers the same pages plus `/api/*`, and one application runs in two profiles: `bench` (owns the log corpus and all analysis) and `drive` (will own the live link from a small in-car node). Clients call `/api/capabilities` and render what the host reports, so live features are added by flipping capabilities rather than restructuring. Commits 6e3cb32 (add), bd84aae and 4ec3686 (web-ui added, then removed: CUORE reached parity and exceeded it).

**2026-09-14 - Evidence gate: a diagnosis verdict needs four criteria.**
Workup dossier, sourced fault trees and a `diagnosis_verdict` gate (demonstrated, mechanism, corpus-verified measurement, disconfirmation). It rejects a DTC offered as a measurement and rejects fabricated citations; "not confirmed" names the missing test from the fault tree. Commit ec5d9cc.

**2026-09-14 - OBD server uses the port lazily, interlocks with MES, gates writes.**
Port and speed resolve from arguments, environment, then MES's own settings; every tool opens the port for one operation and releases it; refuses while MES is connected; raw send rejects embedded line breaks and the batch separator; adapter reconfiguration and vehicle writes sit behind their own flags. Commit 96473d5. The live link (Phase 0) made the OBD server a wrapper over it (091b1c6).

**2026-09-25 - CUORE is the adapter's one owner; buses are verified on demand.**
Fixes for three defects that hid the car (verify flag, legislated route, adapter state leaking between sessions). A transmit session on a bus with no fresh passive-listen proof runs the listen itself and proceeds only if the bus is alive; proofs expire after 600 s. The chassis bus still refuses without explicit confirm. Every OBD MCP read is now a request to CUORE. Commit 0039861.

**2026-09-26 - Per-module clear is consent-gated and evidence-first.**
Typed phrase, stationary vehicle, store everything first, read back, report refusals honestly. No write route over HTTP; MCP only. Commit 3440054.

**2026-09-26 - Test reads cannot become evidence.**
Observations carry their stream; only serial reads count; the audit log honours the state-directory override. 23 scripted reads were purged from the real store (backup kept). Commit 9114102.

**2026-09-26 - MES text is loaded at runtime, never copied into the repo.**
DTC descriptions come from the MES install's language files when present. Commit 169db2a. (Later, on 2026-10-20, the 38 simulation-mode logs were dropped from the captured data snapshot, 2df47fe.)

**2026-09-26 - Live-data engine is read-only; actuator tests are consent-gated.**
Poller for Mode 01 and UDS 22 on CAN-C only (d8115c9); actuator tests have bounded timing and a return-to-ECU check (03a63b8).

## Product shape (2026-10-07 to 2026-10-08)

**2026-10-07 - Alfa Romeo first; marque specifics in data and config; port to Maserati and Ferrari only when asked.**
The target user is a specialist garage working on all three marques. Brand accent is a theme variable; module maps, DID catalogues and spec tables are keyed by platform or vehicle; vehicle detection is VIN-based. Implemented 2026-10-13: `data-marque` is computed from the VIN (alfa, maserati, ferrari), copy is marque-neutral, a Maserati fixture test exists (003d6a4).

**2026-10-07 - Systems layer: every issue is placed in a system and its dependencies.**
25 systems (electrical, fuel, air, cooling, oil, network, ignition, exhaust, driveline, brakes, body, ADAS and others) with dependencies, co-occurrence over time, and a physical layout per system (elements, locations, per-code paths, inspections). Commit 08ca3a0. The dependency layer later gained technical detail on every edge and node (61cf58f, 2026-10-08).

**2026-10-07 - MES-like flow: Job workflow with a hypothesis ledger.**
One logical flow tying driver inputs, mechanic inputs, test results and malfunctions together. Commit 1fc1c7f.

**2026-10-07 - Mechanic feedback on every fact.** Correct, ask, confirm or add input; an Inbox per car. Commit cc07cd9.

**2026-10-08 - Core directive adopted after drift toward shop management.**
Every feature is checked against "diagnose, prove, learn for the next car". Removed from scope: day boards, throughput, blocking gates, inventory. Commits edc447b, 6329aa4 (CUORE.md states what CUORE is and its maxim), d6fa578.

**2026-10-08 - One Job workspace, one step per screen, single column.**
The mechanic hops screens while testing, so the Job page became the single 12-step workspace with every step's content inline; other pages are reference under More. Pages were too long, so one step per screen with a pictogram process map; side-by-side layouts were dropped everywhere. Commits 608e752, 02c1e1f, 41d8219.

**2026-10-08 - Italian-first label dictionary with pictograms, then the chooser removed.**
The first pass added a 64-icon offline SVG set and an Italian-first dictionary because mechanics are often not English-first (98702f0, 02c1e1f). The language chooser was removed the same day and the UI is English only for now (628fe16); pictograms stay.

**2026-10-08 - Marque theme modelled on the premium marque sites.**
Dark, calm, large quiet type, true-black contrast, one accent action, hero band per car; later a typography foundation pass. Commits d5772aa, 2583ef4, ed31772.

**2026-10-08 - Cases: every finished job becomes a case.**
Keyed by model and family; the next same-model car with matching codes gets the prior path, outcome, parts, tools, pitfalls and time. Real cases rank above the seed and are worded "on the last <Model> with these codes". Commits 34ee944, 31c0d71 (2026-10-13, close as case from step 12).

**2026-10-08 - Tools per step with a buy decision card; tool use recorded as memory, not inventory.**
Sourced tool recommendations, owned or not, what was actually used at release. Commit b6cb4b8.

**2026-10-08 - Any code on any system.** A generic sourced isolation tree, open-work cards and hypotheses; EVAP stays the hand-written example. Commit 2e7b8e2.

**2026-10-08 - Release never blocks.** Verified or not, recorded, with an override recorded as "released unverified" and kept visible. Commit d7b9974.

## Live link and scanning (2026-10-13 to 2026-10-19)

**2026-10-13 - Active probe verifies CAN-C behind the Security Gateway.**
Passive listening hears nothing behind the gateway; a Mode 01 PID 00 probe verifies the bus and learns which addressing the ECM answers on. Commit e26b364; first live read 1924adf.

**2026-10-13 - Guided cable-scan wizard.**
Idle, blue A5 (CAN-IHS), grey A6 (CAN-CH), remove cable, summary; plus bus capture, learn and presets, Scans log with diff and health report. Commit d11009f. 2026-10-14: segments accepted out of order (75ab659), fitting the grey cable confirms the CAN-CH sweep (f55c665), a silent bus is "failed" and retryable (92c1773). A segment whose sweep reached no module stays open (48feb5b).

**2026-10-13 - Photo reading is a pluggable service, off by default; LAN bind on.** Mobile "Tell CUORE" page at `/m/{vin}` with a documented API contract. Commits bbcc687, 391e639, 18b3425.

**2026-10-14 - Passive listen uses STMA with ATCAF0 and 11-bit routes.**
The filtered monitor with auto-format on heard 0 frames on the chassis bus where STMA heard 818 in 2 s; Giorgio periodic traffic is 11-bit, so earlier "silent" buses were the monitor, not the car. The "try other bitrates if silent" note was withdrawn after the 2026-10-14 incident. Commit c57de05.

**2026-10-23 - Transmit interlock on cable routes; silence never triggers a send.**
After two functional `3E 00` frames went out at 125k onto the 500k CAN-C bus when the blue A5 cable was pulled (00:50, CAN ERROR, no reply), cable routes and non-500k buses transmit only after at least 5 frames were heard at the declared rate in the last 10 s; the CAN-IHS `3E 00` fallback was removed; a pulled cable is auto-detected (passive 500k listen) and declared `none`; every transmit decision is logged at INFO.

**2026-10-14 - Modifications are a separate layer from diagnostics; coding writes blocked.**
Catalogue (paddle-shift NA to EU first), per-car ledger, MES handoff (7e2eee7). Coding and configuration writes are blocked on every module by service (157177d).

**2026-10-14 - Held scan sessions and multi-PID batching; optional baud raise; pass filters.** After an OBD connectivity review (3883c5a, 157177d).

**2026-10-14 - Typography: marque faces kept, weight 300 for display; the CSS state before the pass is the reference.**
A "`*/`" typo inside a CSS comment had killed the variable block; fixed in c50f90d, faces restored in cffbf8c. Future UI work is incremental.

**2026-10-14 - Transmission data capture deferred until the car is available.**
Needs a full scan (learned TCM DIDs), one MES recording of 8HP parameters, and optionally a second adapter plus Y-splitter to learn DIDs from MES. Software side built (33ae7f1, a6b11ab).

**2026-10-15 - ABS confirmed at 0x2A; identity match may override an unconfirmed registry entry.**
A read-only 29-bit sweep got one reply (VIN match and identity). The registry had ABS at 0x28 and EPS at 0x2A from a forum inference; corrected, with the old inference recorded as wrong. A confirmed clash is still refused. A read-only 11-bit sweep was added (not yet run on the car). Commit 48feb5b.

**2026-10-15 - Bus "awake" judged from the 11-bit listen; query waits never shorter than the adapter's.**
The 29-bit route only hears keep-alive frames whether the car is awake or not. Python-side waits had been shorter than the adapter's 1.02 s reply wait, so two sweeps are not valid negatives. Commit 5ddc799.

**2026-10-15 - Bulletin layer, then cross-reference engine.**
Per-VIN bulletin and recall checklist (0cdd74c); catalogue to 99 rows with cross-reference fields and relation engine (173dc9c). See RULES.md rule 7.

**2026-10-15 - Job actions carry an event date.**
Repairs use the action's event date (not the record time) for already_applied and did_not_resolve; flash bulletins count as applied only when an action says flash, reflash or calibration for the same module; part matches quote the exact token; ruling-out needs the bulletin number plus a ruling-out phrase. Mechanic steps are generated per hypothesis, never auto-saved. Commit 8d9bf34.

**2026-10-15 - Sibling-platform rows are labelled as analogues.**
Sibling-engine bulletins (42 rows) carry a scope and a transferability inference; sibling cars are treated as platform siblings only at the level actually shared. Commits 8d9bf34, e8c8ff3.

**2026-10-19 - Legislated route: the probe always runs on CAN-C; 29-bit first; one retry on the other route.**
After the STMA listen, CAN-C verified on keep-alive frames, so the Mode 01 probe never ran and reads defaulted to the 11-bit route (all NO DATA while UDS reads worked). Commit 4c35d27. Not yet confirmed on the car.

**2026-10-19 - SLVT replica is read-only.**
A re-creation of bulletin 18-048-23's leak verification that uses the same pass criterion as the dealer test (the ECM's own EVAP monitor result: readiness, Mode 06 EVAP test IDs against limits, P0456/P0455/P0440 status bits) and waits for the ECM's own run rather than sending the unpublished routine. Commit bcc62f4.

**2026-10-19 - Scan requirements: every scan reports captured N of M.**
11 machine-checked captures (readiness, Mode 06 EVAP MIDs, PIDs, ECM status bytes, EVAP bundle, ECM identity, battery-sensor DIDs, BCM U-codes, MES clear sync) and 4 mechanic inputs the tools cannot read (ESIM switch state and wire voltage under vacuum, ESIM orientation and part number, SLVT). Legislated NO DATA is reported as the known tool fault. Commit 8edbfe9.

**2026-10-19 - Capture net before anything can erase evidence.**
An EVAP bundle (decoded snapshot, extended data per active EVAP code, Mode 06, readiness) is recorded at every guided scan; every MES log that cleared codes is auto-recorded on the job as a dated action (backfilled once). Commit 8dce38d.

**2026-10-19 - UDS snapshot decoder for ECM and BCM freeze frames** (31eb5b7), with medium confidence stated.

## Diagnosis-state decisions (reference car)

**2026-10-15 - The ECM-calibration verdict was withdrawn.** Bulletin research with the PDFs opened showed the bulletin that lists the EVAP codes as fixed (18-030-17) is for the Giulia only; the Stelvio ECM flash bulletin (18-026-20) lists other codes. The remaining hypotheses moved to the leak-detection signal path. A recall reflash (18V636) became the stronger "was the ECM ever reflashed" lead.

**2026-10-19 - Readings-only verdict.** Leak-detection chain 95 % certain; within it ESIM 35 %, sealed-side leak 25 %, ESIM wiring 20 %, ECM 15 %, other 5 %. No component is proven to need replacement. First physical check is ESIM mounting orientation, then vacuum at the ESIM port with a meter on the switch, then at the ECM pins. Commit f76b758.

## Documentation and data

**2026-10-20 - README rewritten and FEATURES.md added** (447a46f); architecture doc and an ESIM out-of-car bench-test flowchart (c00d221); captured readings snapshot for the reference car with simulation logs removed (4b061cd, 2df47fe).

**2026-10-23 - jobs.jsonl has one live store and one snapshot.** The live store is `C:\ProgramData\cuore\jobs.jsonl`; `data/captures/stelvio-2018/cuore_state/jobs.jsonl` is a snapshot copied after each change. Agents must append to the live store via `mes.jobs` and then copy it over the snapshot; they are different files. Reconciled tonight as a union (208 records, none dropped).

## Corporate acceptance (2026-10-29)

**2026-10-29 - CUORE is the pre-emptive diagnostic tool used before wiTECH; wiTECH keeps the write side and the final word.**
Owner decision after Alfa Romeo corporate authorization and funding were reported granted (owner's words: "we will continue with Cuore as a pre-emptive tool that is used to diagnose before Wi-Tech is engaged as that is an expensive tool to use"). CUORE gathers evidence, ranks hypotheses and proves repairs so the wiTECH session is reduced to what only wiTECH can do. Brand permission (Alfa logos, fonts, graphics) and technical access were reported in the same session; the brand package and the technical documents are awaited before either is used; the 2026-10-27 rule (writes only from documented, authoritative sources) is unchanged. Record: CORPORATE_ACCEPTANCE_2026-10-29.md.

**2026-10-29 - PROXI alignment, battery registration and key learning move into CUORE; AlfaOBD's configuration set is in scope.**
Owner decision after the manufacturer granted technical access: the adjustments that stayed in MES by the 2026-10-26 decision now come into CUORE from the manufacturer's documented procedures, and the coding functions AlfaOBD offers (market settings such as European and North American paddle-shifter usage, comfort and lighting options) join the parity target. Rule unchanged: no learning from captures; documents only. Record: MES_PARITY_PLAN.md, ALFAOBD_GAP.md.
