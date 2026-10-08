# Decisions and rules

## Core directive (check every feature against this)

CUORE is a diagnostic assistant for a mechanic who specialises in one brand and model. Its job is to help him diagnose this car on evidence, prove the repair, and make the next same-model car with the same fault start from what this one taught. The mechanic decides; CUORE advises and records, with sources, dates and confidence. Before building anything, ask: does it serve diagnosing, proving, or learning for the next car? If not, do not build it. No boards, throughput, blocking gates or inventory management.

## Owner's standing rules (2026-09 to 2026-10)

1. The mechanic makes the decisions and the repairs. CUORE supplies the most recent, truthful information with date, source and confidence, labels stale or unverified items, and never invents values.
2. Others' experience matters: every code, family and job carries verified YouTube how-tos and direct forum threads. Forums block plain HTTP checks, so links are verified through a real browser (headless Edge over the DevTools Protocol).
3. Images (photos, scans, borescope video) and audio clips (what a bearing sounds and feels like) are first-class evidence: easy to upload, keep, search and recover.
4. Parts need full detail and images; part sites block automated image checks, so images are verified through the browser and linked, never copied.
5. More interactivity: the mechanic can correct, question, confirm or add input on any fact and see the answer; an Inbox per car tracks it.
6. Systems (25 of them, electrical first) are a correlational dimension for every issue: code to system mapping, dependencies, co-occurrence over time, and the physical layout (wiring, connectors, grounds, boxes, components, locations, conditions) per problem.
7. Align CUORE with a mechanic's technical tool like MultiEcuScan: one logical flow tying driver input, mechanic input, test results and malfunctions together (Job workflow, MES-style Modules view).
8. Printed pages and PDFs must be properly formatted, with an "as of" stamp and sources.
9. Branding: Alfa Romeo first; later ported to Alfa, Maserati and Ferrari. Keep marque specifics in data and config. The Stelvio's sibling cars are the Maserati Grecale (shares the Giorgio platform and GME 2.0T engine family) and Levante (different platform, component-level overlap only).
10. Working method: the main model decides and reviews; low-cost subagents (Sonnet) build. Half the tokens: 4-5 focused checks per feature, one screenshot pass, short reports, one suite run per commit. Commit when agents finish; push only to the `github` remote with the owner's approval; never push to `forge`; never commit koch-mcp/.

## Design decisions

- Safety: no HTTP route ever writes to the car. Clears, actuator tests and routines are MCP-only, need an exact consent phrase (CLEAR <MODULE>, ACTUATE <MODULE> <NAME>, RUN ROUTINE <MODULE> <NAME>), and are refused on blocked modules (ABS, EPS, ORC, HALF, DASM, ESL, TVM, TCM, ESM, DTCM, RFHUB, anything on CAN-CH). The live poller only reads (OBD Mode 01/03/07, UDS 0x22) and every other adapter operation is refused while it holds the port.
- Evidence: the evidence gate counts only measurements from the car (serial stream). Replay, demo, snapshots, symptoms, notes, feedback, media and inspections are labelled and excluded as measurements. Clearing is not fixing: the verdict stays "unverified repair" until a readiness read from the car shows the monitor complete with no code back.
- Verdict and status are computed, never hand-written: ACTIVE FAULTS, UNVERIFIED REPAIR, VERIFIED CLEAN, NO DATA; per code ACTIVE, CLEARED UNVERIFIED, STALE.
- Known-good bands: only one-sided limits (too hot) become gauge warn/alarm bands; idle-only or two-sided ranges show as notes; UNKNOWN stays blank.
- Dossier structure (from the mechanic UX review, implemented 2026-10-07): verdict first, open-work job cards with shared tick state, everything else collapsed with counts, one sticky strip of about 104 px, 16 px body, 44 px targets, dark theme toggle, quick-add note button.
- Family findings: several EVAP codes are one fault; three or more lost-communication codes are one power or bus event (supply and grounds first).
- Recordings stay in MultiEcuScan's CSV format so the existing log tools read them unchanged.
- CUORE runs offline on loopback, kept alive by a per-user scheduled task; no network or Claude dependency.
