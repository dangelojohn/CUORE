# Session record, 2026-09-26 to 2026-10-07 (saved 2026-10-07)

Vehicle: 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115, about 142,290 km / 88,415 mi.
Repo: C:\Users\User\mcp-servers (local main; remote `github` = https://github.com/dangelojohn/CUORE, remote `forge` is unrelated and never pushed to). cuore runs at http://127.0.0.1:5000 under the scheduled task "CUORE Server" (keep-alive, logs in C:\ProgramData\cuore\logs).

## 1. Diagnosis state (truthful, as of 2026-10-07)

- EVAP codes P0455, P0440, P0456 are chronic. The system is physically sealed (three smoke tests) and every EVAP part is new (canister, ESIM, cap, filter, purge valve). The ECM calls a leak when it does not see the ESIM switch report sealed.
- 2026-09-28 scan: P0440 plus U0100, U1713, B1040, C141B, B1176 present; cleared. 2026-09-29 scan: P0440 and B1176 back; cleared 10:46 (SCAN_2609291046). 2026-10-04 engine session 11:16 and scan 11:15 read clean, but both came after the clear and before any monitor could re-run.
- Computed verdict: UNVERIFIED REPAIR. It flips to VERIFIED CLEAN only when a readiness read from the car (serial stream) shows the EVAP monitor complete with no code returned.
- Freeze frames: P0455 set at 93.7 % fuel, P0440 at 91.8 % (EVAP monitor runs only at 15-85 % fuel), P0456 at 80 %.
- Correlation finding: EVAP codes appeared in 12 sessions with no driver symptom reported; network and EVAP codes appeared together in 6 of 18 sessions (lift 0.75). The 28 Sep network/ADAS codes were gone by 29 Sep: one power or bus event. B1176 (rear left window riser) is a separate body fault.
- The MIL is not requested by these codes; "no symptom" is itself the expected pattern for EVAP.
- ECM software P235QB39 / 52170619. Recalls to check by VIN: 25V586000 (fuel pump), 18V636000 (2.0L ECM software). TSB 21-035-20 (TCM flash) applies. TSB 18-030-17 REV. B (PCM flash family includes the EVAP codes), S2125000002 (check the recirculation-line quick-connect first), 18-048-23 (small-leak verification needs wiTECH SLVT or Mode $06).
- Next decisive steps: wiTECH Flash tab comparison, then Test A (vacuum on the ESIM while watching the switch parameter). Do not clear codes until Test A is done.

## 2. Pending items (priority order)

1. wiTECH flash check; Test A; recalls 25V586000, 18V636000; TSB 21-035-20; stop clearing codes.
2. Maintenance from the 2018 US owner's manual (Mopar PDF, CONFIRMED): transfer case oil overdue (80k mi / 128k km / 8 yr); drive belt overdue (36k mi / 4 yr); air filter and spark plugs due at 90k mi; brake fluid every 2 yr; cabin filter 20k mi / 2 yr; coolant 150k mi / 15 yr; engine oil FCA max 10k mi / 1 yr (severe 4k), shop interval 8k mi / 12 mo. All "unless records show it was done": the cuore service ledger is still empty.
3. Enter a baseline maintenance visit and the 2026-09-15 oil change (MES reset, no odometer logged) in cuore.
4. Avery label print check (sample sheet on Desktop; 6576/6578 durable-ID margins unverified).
5. Rear left window riser (B1176); grey-cable (A6) read of the chassis bus modules.
6. Unsourced values: EVAP purge duty and vapour-pressure limits, peak boost, tyre pressures (door placard), P052E/P04DB PCV codes, coil-pack bolt torque, several plug torques (see UNKNOWN rows).
7. Known small bugs: mes/electrical_inspections.py `latest()` does not return the newest record after a second add (one failing check); the vehicle strip's "..." button is partly clipped at 400 px.

## 3. What was built (all committed; GitHub main at cc07cd9 before the systems/electrical/job work)

Dossier redesign per MECHANIC_UX_REVIEW.md (verdict card, open-work checklists with shared tick state, collapsed counted sections, 104 px sticky strip, 16 px body, 44 px targets, dark toggle, logo slot at cuore/web/static/brand/logo.svg); Timeline (codes vs. what the driver notices, symptoms, "what would you feel" table, swimlane SVG with line-style grammar); Tools page (44 curated operations, workflows, writes stay MCP-only); Others' experience (22 YouTube how-tos, 11 browser-verified forum threads, 5 reference sounds); Media library (photos, scans, video, audio with sound tags, search, zip export); Parts catalogue (24 parts, sourced numbers, 9 verified images); Printable report and per-code PDF with print stylesheet; Feedback on every fact plus Inbox; Sibling cars (Grecale shares the Giorgio platform and GME 2.0T family, CORROBORATED; Levante is on the Ghibli-derived platform, component-level overlap only); Known-good bands (one-sided limits only become gauge bands); Routine maintenance area; Service hub; Gauges; Labels; launchers and keep-alive.
In progress today (uncommitted at the time of this record): Systems layer (25 systems incl. PCV, dependencies, co-occurrence, Systems tab), Electrical layout (elements, per-code paths, inspections, Electrical tab) generalised to all systems (76 placed elements), Job/case workflow with hypothesis ledger, MES-style Modules view.

## 4. Standing rules from the user (also in Claude memory)

- Fable (the main model) is for decisions and review only; all building goes to low-cost subagents (Sonnet). Use half the tokens: 4-5 focused checks per feature, one screenshot pass, reports under 100-120 words, one suite run before each commit. Never Fable forks.
- Commit when agents finish; push to `github` only (user approves each push); never push to `forge`; never commit koch-mcp/.
- The mechanic makes the decisions and repairs; cuore supplies the most recent, truthful information with date, source and confidence; stale or unverified items are labelled; never invent values (UNKNOWN means "use the service manual, TechAuthority").
- Every error, family and job carries others' experience: verified YouTube how-tos and direct forum threads. Forums block plain HTTP checks (202 bot wall): verify through headless Edge over CDP.
- Images (photos, scans, borescope video) and audio clips are first-class evidence; parts need detail and images; printed pages must be properly formatted with an "as of" stamp.
- More interactivity: the mechanic can correct, ask, confirm or add input on any fact and see it answered.
- Systems (electrical, fuel, air, lubrication, cooling, EVAP, PCV, and the rest of the 25) are a correlational dimension for every issue; the physical layout (wiring, connectors, grounds, boxes, locations, conditions) is identified per problem, electrical first, then every system.
- CUORE is Alfa-branded first; later ported to Alfa, Maserati and Ferrari: keep marque specifics in data and config.
- Align cuore to a mechanic's technical tool like MultiEcuScan: one logical flow tying driver input, mechanic input, test results and malfunctions together.

## 5. Methods and gotchas found

- Headless Edge: CLI --dump-dom and --screenshot do not work on this PC; drive it over the DevTools Protocol (cuore/tests/check_live_widgets.py pattern) and kill it by its temp --user-data-dir (cuore/tests/_edge_cleanup.py), or 266 processes leak.
- Jinja: a dict key named "items" is shadowed by dict.items(); use bracket access or rename.
- cuore health endpoint is /api/health; the keep-alive identifies cuore by its health body; cmd /c needs extra outer quotes.
- Agent-driven `git push` is blocked by the permission classifier; the user approves a direct push in manual mode.
- MES language files hold only description fragments; the code-to-text map is in MES's encrypted database (left alone).
- Tests must set CUORE_STATE_DIR to a temp dir before importing cuore; media, feedback, symptoms, checklists, inspections and jobs are attested records, never car measurements.

## 6. One-page sheets in this folder (pdf/, generators in pdf-sources/)

Dossier, Pending Items, Service Hub, Routine Maintenance, General Service Record, Oil Change, Brakes Wheels Tyres, Transmission and Drivetrain, Torque Settings, Drivetrain Torque Settings, Gauges, Service Labels, Sample Service Labels, Mechanic Notes, Vehicle Dashboard, wiTECH Test A (1 page and full), wiTECH Flash Check, ECM Flash Procedure, ESIM Bench Test, ESIM Wiring Test, ESIM Wiring Diagram Lookup, Recalls and Campaigns.

## 7. Addendum (later on 2026-10-07)

Committed and pushed (GitHub main at the "Handbook: architecture" commit): Systems layer (25 systems) with Systems tab and by-system timeline; Electrical tab generalised to all systems (76 placed elements) with per-code physical paths and inspection records; Job workflow with hypothesis ledger (EVAP: ESIM signal path, EVAP: ECM calibration, network, each with real evidence refs); MES-style Modules view; the inspections `latest()` bug fixed. Handbook created at docs/handbook/ (decisions, architecture, knowledge tables, Stelvio case, methods, roadmap). All suites green at commit time. cuore restarted to serve the new tabs.
