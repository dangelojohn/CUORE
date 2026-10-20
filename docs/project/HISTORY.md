# History

Changelog grouped by month, summarised from git history (219 commits, 2026-08-27 to 2026-10-20) and the session records in `docs/sessions/`. Not every commit is listed.

## 2026-08

- 2026-08-27 Rebuilt the MES log bridge as a structured diagnostic library (eca5d08); added platform research and clinical findings to the analysis layer (d124f3a).
- 2026-08-27 Closed the biggest MES gap: OBD-II readiness monitors (11de50c); fixed three silent-wrongness bugs and a safety hole in the OBD server (198a2be).
- 2026-08-27 Reference material: EVAP reference ("the repair cannot be verified by road test", 33283bb), ZF 8HP and Magna Q4 reference (31c74ae), OEM 8HP service data correcting widely repeated numbers (1939c26), network-cascade causes reordered against the manufacturer's own bulletins (4e627d6).

## 2026-09

- 09-02 Added CUORE, the companion service over the `mes` library (6e3cb32); a Flask web-ui was added and removed the same day once CUORE exceeded it (bd84aae, 4ec3686); bay-tablet mockup (d8ea63e).
- 09-14 MES deep-integration review (426b676); workup dossier, fault trees, evidence gate and CSV recordings (ec5d9cc); OBD server reworked for lazy port use, MES interlock and gated writes (96473d5); CUORE live-link plan, Giorgio module map and Phase 0 live link (65cce8b, 091b1c6); line endings pinned (9302dbd).
- 09-15 Launcher, one active vehicle with a merged module view and grouped navigation, gate wired to the live link, "try every route a cable allows before calling a bus silent", MES interlock ctypes fix (5ee0cd5, a38c07f, b81f89f, eebdb48).
- 09-25 CUORE made the adapter's single owner; bus verification on demand; whole-car coverage session (0039861).
- 09-26 Largest single day (32 commits): per-module clear with evidence, Mode 06, DTC detail, readable-item catalogue and passive wiTECH learning (3440054, 5fba281); dealer results import (1845666); EVAP smoke-test procedure and fault-tree dealer check (0e9cfd0, f0cc13d); the reference-car EVAP case file saved (4647726); test reads kept out of evidence (9114102); live-data engine and Gauges with live, replay and demo sources (d8115c9 to 97bff30); notes, vehicle dashboard, actuator tests, service records, drivetrain and service hub, printable service labels; keep-alive scheduled task, launcher improvements, browser-test leak fix (7389235, 8896afd, 9375d48).

## 2026-10

- 10-01 One-page sheets for wiTECH test A and pending items (5144915, d7b7dd3); keep-alive logs skipped launches (385b816).
- 10-07 Dossier view model with computed verdict and family checklists (8e5bc2d), mechanic UX redesign (2bec950); media library, parts catalogue, mechanic feedback store (2e21355, cc07cd9); printable car report and per-code PDFs (efa8893); audio clips and sibling-car data (7e05223); tools page (c342a92); systems layer and physical layout for every system (08ca3a0); Job workflow with hypothesis ledger (1fc1c7f); handbook with decisions, rules and roadmap (f0d9dfe); case folder session record 2026-09-26 to 2026-10-07 (b5f758c); label offset calibration (6ac133e).
- 10-08 Core directive and CUORE.md (edc447b, 6329aa4); Start and Release (d7b9974); tools per step (b6cb4b8); cases (34ee944); generic any-code isolation trees (2e7b8e2); Job as the single 12-step workspace (608e752) then one step per screen, single column, pictograms, marque theme and emphasis pass (02c1e1f, 41d8219, 98702f0, d5772aa, 2583ef4); performance caching (job page 9 to 12 s down to 0.3 s: d2e31cd); Bench landing screen (406e175); Tests surface with 38 sourced tests (5f0957f); Job rules with guided hypothesis status path (ccb8ade); Systems phases 3-4 and dive-in page (1e7091a, 32a2964); mechanic reviews and UX specs saved to research.
- 10-13 First live read from the reference car with the active probe and 29-bit legislated route (e26b364, 1924adf); Tell CUORE mobile page, LAN bind, photo-reading service off by default (391e639, bbcc687, 18b3425); case close from step 12 (31c0d71); marque port groundwork (003d6a4); full live scan orchestrator (f217020); guided cable-scan wizard, bus capture and learn, scan plan and diff page (d11009f).
- 10-14 (63 commits) Overnight UI and live-link passes: typography foundation and the CSS comment typo found and fixed (ed31772, c50f90d, cffbf8c); modifications layer (7e2eee7); MES vs CUORE capability matrix and CUORE log tools (545abb8, 574e9b9); transmission surface and MES-learn from a second adapter (33ae7f1, a6b11ab); connect-to-car inline guided scan (b87ecfe); MIL diagnostics and clear-assessment fix (2210d76); multi-PID batching and held sessions (157177d, 3883c5a); guided-scan segment behaviour (75ab659, 92c1773, 89629b2, f55c665); passive listen fixed with STMA and 11-bit routes (c57de05); external and mechanic review rounds 5 to 7 folded in. Incident late that night: a raw serial script on the wrong bitrates lit warning lamps (see RULES.md rule 4).
- 10-15 Chassis-bus findings: ABS confirmed at 0x2A, identity override, 11-bit discovery, awake judgement, timing fix (48feb5b, 5ddc799); session records (bd4ebee, e8abe8f); bulletin layer, cross-reference engine and catalogue to 99 rows (0cdd74c, 173dc9c); mechanic steps per hypothesis, event dates, sibling analogues (8d9bf34); engine, battery and bus facts (937a5cf).
- 10-19 Check-engine-lamp visit: legislated route fix (4c35d27); UDS freeze-frame decoder (31eb5b7); CEL diagnosis write-ups, ranking and readings-only ledger (e1e0c68, 821e436, 88e6c96, f76b758); SLVT replica page (bcc62f4); capture net (8dce38d); scan requirements (8edbfe9).
- 10-20 Architecture document and ESIM out-of-car bench-test flowchart (c00d221); captured readings snapshot for the reference car, simulation logs removed (4b061cd, 2df47fe); README rewritten and FEATURES.md added (447a46f); this project record.

## Session records

- `docs/sessions/2026-10-13-agent-discoveries.md` (43 agent reports), `2026-10-14-agent-discoveries.md` (11 reports): durable digests of what each helper built or found, generated by the backup scripts. Raw transcripts are under `docs/sessions/raw/`.
- `docs/sessions/2026-10-15-chassis-bus-discoveries.md`: what was learned on the car about the chassis buses and the listen and discovery path, the 2026-10-14 incident, open questions and next tests.

## Research documents (titles by theme)

- Diagnosis: EVAP fault tree and smoke test, CEL 2026-10-19 diagnosis, actuator tests, ECU tuning IAW 10JA, ZF 8HP and Q4, WiTECH passive learning, diagnostic assurance framework.
- MES: capability gaps, deep integration review, integration surface, MES vs CUORE capability, paddle-shift coding.
- Platform and connectivity: Giorgio platform, connectivity and the Security Gateway, OBD connectivity review, sibling platforms bus topology, live-data UX survey, specs research.
- Reviews and UX: mechanic reviews 1 to 7, external review 6, bench and job UX specs and fixes, systems dive-in plan, type and UI audit, marque port audit.
