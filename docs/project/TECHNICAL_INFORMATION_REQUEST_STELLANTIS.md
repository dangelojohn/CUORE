# CUORE: Technical Information Required from Stellantis

2026-10-30 · CUORE project owner

Local copy of the shared document https://claude.ai/artifact/9oAUQL8iASegDUzLLuZzWJ (written 2026-10-30 for submission to corporate).

## Purpose and how to read this request

CUORE needs the manufacturer's diagnostic definitions, procedures and service information listed below to do every job a technician now does in MES, AlfaOBD or wiTECH's pre-flash diagnostics, safely and on documented sources. The one read-only session on the reference car (the 13-step Bench plan) confirms what CUORE can already read; it cannot supply the definitions, procedures and security access that only Stellantis holds.

CUORE is a diagnostic workbench for Alfa Romeo, Maserati and Ferrari technicians, used before wiTECH. It reads modules over UDS on a low-cost USB adapter, diagnoses on evidence, and proves repairs by read-back. Reference car: 2018 Alfa Romeo Stelvio 2.0T (949), VIN ZASFAKPN5J7B88115, an Alfa Romeo Canada loaner. Today CUORE covers 32 of the 98 functions technicians use; 49 of the remaining 66 wait on the information in this request.

**Priority tiers used throughout**

- **P1:** needed to finish the reference car and run CUORE's first documented writes (resets, battery registration, configuration, keys).
- **P2:** needed for full diagnostic depth on the 949 and 952 platform (every module, every code, every test).
- **P3:** needed to scale to other models, marques and markets.

**Preferred formats**, in order: ODX 2.2 / PDX (ISO 22901) or CANdela CDD diagnostic descriptions per module and software version; DBC communication matrices for broadcast signals; structured exports (CSV, JSON, XML) for lists; PDF service information. Everything is stored per platform as data with its source document and date, never hard-coded, and is not republished outside CUORE without a written agreement.

**Scope of the first request:** Giulia 952 and Stelvio 949, model years 2017 to 2026, North American and European markets. Section H lists the same package for other models and marques.

## A. Vehicle networks and diagnostic access

CUORE reaches CAN-C through the OBD port and CAN-IHS and CAN-CH only through aftermarket bypass cables. It needs the documented network and the sanctioned way to reach every module.

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| A1 | Network topology per platform and model year | Every bus (CAN-C, CAN-IHS, CAN-CH and any others), bitrates, which module sits on which bus, gateway routing rules, which modules answer diagnostics from the OBD port | P1 |
| A2 | Diagnostic addressing per module | Physical request and response CAN IDs (11- or 29-bit), functional addressing, ISO-TP parameters (block size, STmin, padding), timing (P2, P2*, S3 tester-present) | P1 |
| A3 | Secure Gateway | Which model years and markets carry one; the authentication process (North America and the EU / SERMI scheme); the API a third-party tool uses; how CUORE becomes an authenticated tool | P1 |
| A4 | Sanctioned access to the non-OBD buses | Whether diagnostics to CAN-IHS and CAN-CH modules can be routed through the gateway, or the approved physical access point | P2 |
| A5 | Interface hardware requirements | Minimum adapter specification (J2534, STN-based USB adapters), whether low-cost adapters are acceptable for reads and for writes, and battery-support requirements during writes | P1 |
| A6 | Bus load and safety limits | Maximum request rate per module, tester-present rules, behaviour of modules during flashing, what a listen-only tool must never do | P2 |

## B. Diagnostic data definitions per module

This is the core of the request: the diagnostic description of every module, per software version, ideally as ODX/PDX or CDD. Today CUORE has one confirmed scaling out of about 133 engine-computer values MES shows.

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| B1 | Module list | Every module per platform and model year: name, acronym, supplier, part numbers, software versions in the field | P1 |
| B2 | Diagnostic sessions | Supported sessions (0x10) per module, and which services need which session | P1 |
| B3 | Data identifiers (0x22) | Every identifier: name, length, data type, scaling and offset, units, enumerations, required session and security level | P1 |
| B4 | Writable identifiers (0x2E) | Which identifiers are writable, allowed values and ranges, the read-back identifier, preconditions | P1 |
| B5 | Routines (0x31) | Every routine: identifier, purpose, start/stop/result parameters, preconditions, duration, polling and result codes | P1 |
| B6 | Input/output control (0x2F) | Actuator tests: identifiers, allowed states, maximum duration, safety interlocks (engine running, speed, gear) | P2 |
| B7 | Security access (0x27) | Levels per module and which functions need them; the seed/key algorithm or an authenticated key service; attempt limits and lockout timers | P1 |
| B8 | Fault codes (0x19) | Full code list per module including B, C and U codes; official text; failure-type bytes; status-bit meaning; set, mature, heal and aging conditions; lamp logic | P1 |
| B9 | Snapshot and extended data | Freeze-frame (snapshot) record layouts and extended data records, including ABS environmental data and occurrence counters | P2 |
| B10 | Identification identifiers | ECU identification (F18x / F19x range): VIN, part, hardware, software and calibration numbers, and how they map to the current calibration level | P1 |
| B11 | Negative responses | Module-specific negative response behaviour and recommended tester reactions | P2 |
| B12 | Clear rules | When clearing codes is allowed per module and what it resets (readiness, adaptations, counters) | P2 |

## C. Vehicle configuration (PROXI)

CUORE can read the Body computer's configuration block but can name only two bytes, both from single forum posts. The paddle-shifter market switch (Europe or North America) and every coding function wait on this section.

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| C1 | PROXI data map | Per platform and model year: the identifier(s) holding the configuration, length, every byte and bit with its meaning, allowed values, defaults per market, dependencies between settings, any checksum | P1 |
| C2 | Which modules hold copies | The module roster that compares against the Body computer, and what each does on a mismatch | P1 |
| C3 | PROXI alignment procedure | Routine identifiers, order, preconditions (battery support 13.2 to 13.5 V, engine off), duration, failure handling, recovery from a partial alignment | P1 |
| C4 | Restore Vehicle Configuration | Where the as-built configuration comes from (by VIN), how it is retrieved and written, and who may do it | P1 |
| C5 | Build data by VIN | Option and sales codes, market, trim, and their mapping to configuration bits | P2 |
| C6 | Market settings dealers ask for | The documented settings for paddle-shifter market behaviour, units, lighting, comfort and chimes: which are allowed to change and which are type-approval locked | P1 |

## D. Service and adjustment procedures

For each procedure CUORE needs the same five things: preconditions, the steps in diagnostic terms (session, security level, identifiers or routines, values), the read-back that proves the result, failure handling and recovery, and whether a dealer-only authorization applies. CUORE already holds definition files for the first fifteen, all with empty steps.

| Procedure | Module | Priority |
| --- | --- | --- |
| Oil life and service interval reset | Instrument cluster / engine | P1 |
| Overboost counter reset; turbocharger replacement reset | Engine | P1 |
| Battery type registration and battery sensor (IBS) reset | Body computer / power management | P1 |
| PROXI alignment and Restore Vehicle Configuration | Body computer and all configured modules | P1 |
| Paddle-shifter market behaviour (Europe / North America) | Body computer | P1 |
| Key learning, key deletion and immobilizer procedures | RF hub / immobilizer | P1 |
| ABS / ESC brake bleed (service and HCU routines) | Brake system | P1 |
| TPMS reference pressures and sensor learning | TPMS / RF hub | P1 |
| Cornering lamps, AFTER WIPE, window comfort, seat-belt chime, Race mode in DNA | Body and lighting modules | P2 |
| Throttle body (ETC) learn and engine adaptation resets | Engine | P2 |
| Transmission adaptation reset and quick learn (8-speed automatic) | Transmission | P2 |
| AWD and transfer case calibration | AWD module | P2 |
| Steering angle sensor calibration | Steering / chassis | P2 |
| Electric parking brake service mode | Brake system | P2 |
| Headlamp levelling and adaptive lighting calibration | Lighting | P2 |
| ADAS camera and radar calibration (static and dynamic) | Driver assistance | P2 |
| MultiAir actuator replacement learn | Engine | P2 |
| Window, sunroof and seat memory initialisation | Body | P3 |
| New-module installation (VIN write, configuration, coding, learn) | Any replaced module | P2 |

Where a procedure needs flashing or the manufacturer's server, CUORE hands the car to wiTECH; please mark those so CUORE can tell the technician before they start.

## E. Emissions and OBD

The reference car's EVAP case showed why this matters: CUORE could not prove the leak-check monitor had run, because the enabling conditions are not published.

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| E1 | Mode 06 definitions | Test and monitor identifiers, scaling, units and limits for the engine computer in each market | P1 |
| E2 | Monitor enabling conditions | Per monitor (EVAP, catalyst, oxygen sensors, EGR, misfire, fuel system): fuel level window, temperatures, soak times, drive patterns | P1 |
| E3 | Drive cycles | The documented drive cycle to complete each monitor and set readiness | P1 |
| E4 | Permanent codes | Conditions that erase each permanent code | P2 |
| E5 | Calibration identifiers | Mode 09 calibration IDs and verification numbers mapped to the released calibration levels | P2 |
| E6 | EVAP system specifics | Leak-check module (ESIM) operation, its diagnostic identifiers and service tests | P1 |

## F. Broadcast signals for live data

CUORE decodes live chassis and body data by listening to the buses, and today learns each signal by experiment, with scaling marked unknown. A communication matrix replaces guesswork with documented values.

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| F1 | Communication matrix per bus | DBC (or equivalent): message IDs, period, sender, signals with start bit, length, byte order, scaling, offset, units, value tables | P2 |
| F2 | Signal list for live gauges | Wheel speeds, steering angle, yaw, brake pressure, gear, torque, temperatures, door and lamp states, with their source module | P2 |

## G. Service information, software levels and vehicle records

TechAuthority (North America) and stellantisiop.com (Europe) are expected to cover most of G1; the rest needs a data feed or an agreement.

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| G1 | Service information | Wiring diagrams, connector views and pinouts, component and ground locations, fuse and relay maps, specifications, diagnostic test procedures per code | P1 |
| G2 | Bulletins and cases | Full bulletin texts and STAR-style case resolutions for the 949 and 952 | P1 |
| G3 | Released software levels | Current calibration per module and the bulletin that released it, so CUORE can tell a technician a module is out of date and needs wiTECH | P2 |
| G4 | Recall and campaign status by VIN | Open and completed campaigns, through an API or export | P2 |
| G5 | Machine-readable access | An API or bulk export for G1 to G4 instead of page-by-page reading | P3 |

## H. Other models and marques

The same package (sections A to G) for each model in scope, delivered as data per platform so each model is an import, not new code.

- **Alfa Romeo:** Giulia 952 (all trims, including Quadrifoglio), Stelvio 949 (including Quadrifoglio), and any further models Alfa Romeo wants covered.
- **Maserati:** the models in scope for CUORE, to be named by Maserati.
- **Ferrari:** the models in scope for CUORE, to be named by Ferrari.
- **Markets:** Canada, the United States and Europe first; market-specific settings, units and code text.

## I. Agreements, licensing and contacts

| # | Request | Detail needed | Priority |
| --- | --- | --- | --- |
| I1 | Written authorization | Scope of CUORE's authorization, markets, and the functions it may perform, including writes | P1 |
| I2 | Data licence | Terms for using the information above inside CUORE and distributing it to dealers and independent shops; a re-publishing agreement where needed | P1 |
| I3 | Write liability and approval | Who approves each write procedure before release, and the sign-off process | P1 |
| I4 | Recording wiTECH | Written permission to record wiTECH's diagnostic traffic on the reference car, and dealer time for those sessions | P1 |
| I5 | Brand use | Written terms for the Alfa Romeo, Maserati and Ferrari logos, fonts and graphics in CUORE | P2 |
| I6 | Tool approval path | How CUORE becomes a recognised tool for dealers and for independent operators, including Secure Gateway authentication | P2 |
| I7 | Engineering contact | A named diagnostic-engineering contact for questions and escalations | P1 |
| I8 | Customer data | Data-protection requirements for VINs and customer records held in CUORE | P2 |

## Summary: what each request unlocks

The P1 items let CUORE finish the reference car and perform its first documented writes; P2 gives full diagnostic depth; P3 lets it scale.

| CUORE capability | Requests | Result for technicians |
| --- | --- | --- |
| Read every module with the manufacturer's names and values | A1, A2, B1 to B3, B10, F1 | Same or better coverage than MES on every module |
| Explain every fault code | B8, B9, E1 to E4, G1, G2 | Official code text, snapshots, test steps and bulletins in one place |
| Service resets and registrations | B4, B5, B7, D | Oil, service, overboost, battery and TPMS jobs done in CUORE, proven by read-back |
| Configuration and market settings | C1 to C6, B7 | PROXI read named in full; the Europe / North America paddle switch and other coding |
| Keys and immobilizer | B7, D, I1, I3 | Key learning in CUORE under the manufacturer's authorization |
| Actuator tests | B6 | Component tests from the workbench |
| Know when to hand off to wiTECH | D, G3 | CUORE tells the technician before they start when flashing or the server is needed |
| Deploy to dealers and independent shops | A3, A5, I2, I6, I8 | One approved standard tool on low-cost hardware |
| Other models and marques | H | Giulia, Maserati and Ferrari as data imports |

Contact for this request: the CUORE project owner. Every item received is recorded with its source document and date, used only inside CUORE under the agreed terms, and shown to the technician as the manufacturer's information.
