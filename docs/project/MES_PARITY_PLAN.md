# MES parity plan: what closes the gap so CUORE is the mechanic's first tool

Date: 2026-10-29. Owner's framing: "mes is not official but cuore is. what do we need to do to close the gap to be able to be fully used as cuore is, so that cuore is the first mechanic's tool to fully diagnose and repair the same items that mes can and then the mechanic can go to expensive wi-tech for next level support."

Target state: a technician opens CUORE first for every Alfa Romeo, Maserati or Ferrari job. CUORE reads everything MES reads, performs the adjustments MES performs (resets, actuator tests, calibrations, codings), proves each one by read-back, and hands the car to wiTECH only for what needs the manufacturer's own server: flashing, programming, secured configuration, warranty authorisation.

This plan is built on the gap inventory of 2026-10-27 (CUORE notes c9c9dd720c01 writes, dcb76d25442b reads, fc047a665508 features), the session kits of 2026-10-28 (note b31c5c5cd2a6), the write-path design (docs/design/CUORE_WRITE_CAPABILITY_PLAN.md, CUORE_ADJUSTMENTS_PLAN.md, CUORE_INTERACTIVE_PROCEDURES_DESIGN.md) and the corporate acceptance of 2026-10-29 (CORPORATE_ACCEPTANCE_2026-10-29.md). Everything below that touches the car's data is a read until the documents in section 1 arrive.

## Where the gap is, in one table

| Area | MES today | CUORE today | What closes it |
|---|---|---|---|
| Reads: codes, freeze frames, live data, Mode 06 | 12 modules on the reference car; per-module parameter lists; decoded freeze frames | 5 modules usable (ECM, TCM, BCM, IPC, RFHUB), ABS identity only; about 31 ECM DIDs with 1 confirmed scale against 133 MES names; freeze-frame layouts for ECM and BCM only | Section 1 items 1 and 4 (DID and snapshot definitions); section 2 car session; without documents, the session kits learn it the slow way |
| Writes: service and oil resets, counters | Done in MES on 2026-06-07, 09-15, 10-23, 10-24 | Definition files with empty steps, status "awaiting source"; 0x2E and 0x27 refused by three layers by design | Section 1 item 2, then section 3 |
| Actuator tests | EVAP valve, EGR, wastegate, turbo vacuum valve completed in MES; thermostat and fan failed | Replay engine built, zero procedures | Section 1 item 2 (routine identifiers), then section 3 |
| Security-coded functions (BCM commands, key and remote learning) | MES asks a security code | 0x27 refused everywhere | Section 1 item 1 (security access), decision in section 3 |
| PROXI alignment, battery registration, coding | MES | Stay in MES by the 2026-10-26 decision | Section 1 item 2; owner decision whether they move to CUORE or count as wiTECH next level |
| Buses and cables | CAN-C plus A5 (blue) and A6 (grey) bypass cables | Same cables; CAN-CH 28 sessions, CAN-IHS probes only; no code or parameter ever read on a bypass bus | Section 2 steps on the grey cable; section 1 item 5 for a cable-free path |
| Day-to-day features | Monitor DTCs, tags, F7 adjustments screen, security code entry | Code watch, tags, priorities, graphs, sort built 2026-10-28; adjustments screen absent | Section 3 (adjustments screen) |
| Evidence and workflow | None | Job, hypotheses, fault board, proof of repair, TSB cross-reference, systems map, parts catalogue | Already ahead of MES; keep |

## 1. What we need from Stellantis (the technical access that was granted)

The 2026-10-27 rule stands: CUORE never learns a write by capturing MES or AlfaOBD; every write comes from a documented, authoritative source with a citation. The manufacturer's technical access is that source. The ask, in priority order:

1. **UDS diagnostic specification per module** for the Giorgio platform (ECM Marelli IAW 10JA, IPC, BCM, TCM ZF 8HP, ABS Continental MK C1, ESM, DTCM, DASM, RFHUB, HVAC, ETM, PAM, HALF, AFLS): diagnostic addresses on each bus (29-bit and 11-bit), diagnostic session types, security access (service 0x27 seed-key algorithm, or whatever authentication the module uses), the readable DID list with scaling and units (service 0x22), routine identifiers for actuator tests and calibrations (service 0x31), writable DIDs for resets (service 0x2E), and for every write the DID that proves it (read-back).
2. **Service procedures as the manufacturer performs them**: oil change reset (ECM), service interval reset (IPC), overboost counter and turbocharger replacement reset, battery registration and IBS, PROXI alignment, key and remote learning, throttle and learned-value resets, steering angle calibration, ABS bleed and calibration routines, and the conditions each one requires (engine state, speed, temperature).
3. **OBD Mode 06** test identifiers and scaling for the Marelli ECM, so every on-board test result reads as a number with a limit.
4. **Fault memory definitions**: official DTC descriptions per module and market, 19 04 snapshot (freeze frame) layouts per module, the meaning of 19 06 occurrence and ageing counters, and the ABS environmental data block.
5. **Network and access**: confirmed module-to-bus assignment, and the sanctioned way to reach the chassis and interior buses without bypass cables on 2018 and later cars (what wiTECH does through the gateway; see docs/research/CONNECTIVITY_AND_SGW.md for what was established on the reference car). A supported interface list for dealers belongs here too.
6. **Service information**: wiring diagrams, connector pinouts, component locations, fuse and relay maps, and TSB access, so the electrical paths and layouts CUORE draws stop being inferred.
7. **Model data for the other marques**: the same package for the Maserati and Ferrari models in scope, keyed the same way (platform, model, year).

Everything arrives as data under cuore/data keyed by platform, never as code. Each item carries its source document and date.

## 2. What CUORE does now, without waiting (one car session, read-only)

The Bench "Next connection" plan already holds the 13 steps (note b31c5c5cd2a6). In parity terms they deliver:

- Confirmed decodings for the parameters MES and CUORE share (tags 1 to 4, decode_confirm), lifting the suspect flags on throttle, boost voltage and boost required.
- Every responder on CAN-C named and its address confirmed (discover, name_responders, accept_responder), settling the DTCM, ESM and DASM addresses.
- Code rounds with snapshots and counters on IPC and TCM, then ESM and DTCM once accepted.
- The first ABS code round and freeze-frame bindings on the grey cable.
- Mode 06 record layout checked against a live reply.

After that session CUORE reads what MES reads on the modules it can reach. The remaining read gaps (HVAC, ETM, PAM, HALF, AFLS, and the full MES parameter lists) are data-entry once section 1 items 1 and 4 arrive.

## 3. What CUORE builds once the documents arrive (the designed write path)

The write path was designed in stages and is partly built. In order:

1. **Procedure definitions from documents.** Each reset or test is a JSON file in cuore/data/procedures with its steps, the session and security requirements, the read-back DIDs and the citation (the schema and the acceptance log already exist: cuore/live/procedure_sources.py, procedure_acceptances.jsonl). The two scaffolds (engine_oil_reset, service_interval_reset) get their steps first.
2. **Security access from the documented algorithm.** Service 0x27 stays refused until a per-module, cited implementation exists; then it is allowed only inside a defined procedure, never from raw send.
3. **The gate, unchanged.** Dry run, vehicle-state checks, typed consent phrase, execution, read-back, audit record. Allowlisting 0x2E and 0x31 per procedure is an owner rule change recorded in RULES.md.
4. **Web execution with a lock.** Today writes are MCP-only with no web button. Technicians need them in the web app: the hold-to-start token and the acceptance record (not yet built) guard a procedure page that shows the source, the dry run, the consent and the read-back result.
5. **Adjustments screen** (MES F7 equivalent): one list per module of the procedures available for this car, each with its status (documented, accepted, performed, verified), its source and what it writes and reads back.
6. **Actuator tests** from the documented routine identifiers into the existing replay engine (EVAP valve, EGR, wastegate, turbo vacuum valve first, because MES proved they run on this engine; thermostat and fan after the documents explain why MES failed).
7. **Owner decision 2026-10-29: PROXI alignment, battery registration and key learning move into CUORE** ("as does MES"), from the manufacturer's documented procedures. Also in scope: the configuration and coding functions AlfaOBD offers, such as the European and North American paddle-shifter settings (docs/project/ALFAOBD_GAP.md). Still open: whether the chassis bus is used through the gateway or the cable.

## 4. Proving parity (so "fully used" is a measured claim)

- **Parity board.** A Bench page listing every MES function from the capability matrix (docs/research/MES_VS_CUORE_CAPABILITY_2026-10-14.md and the inventory notes) with one of four states: done in CUORE, needs a car session, needs documents, decision pending. It is the agenda for the manufacturer meetings and the release checklist.
- **Side-by-side test on the loaner.** For each read function: the same codes, the same values within the decoding tolerance, recorded as a CUORE observation with the MES log cited. For each write: CUORE performs it, reads back, and the next MES read shows the same state. Nothing is marked done without that record.
- **Exit criterion for MES.** When every row that a dealership technician uses is "done in CUORE" with a recorded test, MES comes off the bench PC and the interlock code becomes dead code.

## 5. Beyond the reference car

- Data keyed by platform and model (the 949 and 952 first), so the Giulia is a data import, not a rewrite; Maserati and Ferrari follow the same shape once their packages arrive.
- A supported interface list for dealers (the consumer vLinker adapter on COM3 proved the concept; its limits, 6 PIDs per frame and the 18 V risk on pin 13 with the grey cable, are recorded).
- Market settings: units, language, DTC text per market, from section 1 item 4.

## AlfaOBD

The owner's history (2026-10-29): AlfaOBD nearly became the official tool a few years ago, then MES surpassed it as the mechanics' go-to tool; CUORE now takes that place and needs mechanic adoption. AlfaOBD's configuration set (market settings such as paddle-shifter usage, comfort and lighting options through PROXI) is therefore part of the parity target; the AlfaOBD gap study is docs/project/ALFAOBD_GAP.md. The rule is unchanged: nothing is learned by capturing AlfaOBD; the PROXI data and procedures come from the manufacturer.

## Order of work

1. Now: the car session (section 2) and the parity board (section 4), both without documents.
2. On receipt of section 1 items 1, 2 and 4: service resets, actuator tests, adjustments screen, web lock (section 3), then the side-by-side test.
3. On receipt of items 5 and 7: cable-free bus access and the other marques.

What makes CUORE official is not the badge: it is that every function cites the manufacturer's document and proves its result on the car. That is the gap MES can never close, and the one this plan closes.
