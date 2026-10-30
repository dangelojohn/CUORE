# Rollout plan: CUORE as the technician's standard

Written 2026-10-30 for the Alfa Romeo representative. The goal, as the representative stated it through the project owner: CUORE becomes the one diagnostic tool every service technician uses, at Alfa Romeo dealers and at independent shops, in place of today's mix of MultiEcuScan (MES) and AlfaOBD, whose results have been poor. Maserati and Ferrari follow. Statements attributed to the manufacturer are owner-reported; no written agreement is on file yet (see Corporate Acceptance 2026-10-29 (wiki: Corporate-Acceptance-2026-10-29)). The same plan is on the GitHub wiki as Rollout-Plan.

## What the standard means

A technician at any Alfa Romeo shop plugs in a low-cost USB adapter, opens CUORE, and:

1. reads every module MES reads, with the manufacturer's names and values;
2. diagnoses on evidence: every conclusion cites a reading CUORE captured, linked to the bulletins and the wiring for that fault;
3. performs the service functions MES and AlfaOBD perform (resets, battery registration, configuration, key learning) from manufacturer-sourced procedures, each proven by read-back;
4. proves the repair on the car before the customer leaves;
5. hands the car to wiTECH only for what needs the manufacturer's server: flashing, secured programming, warranty authorisation.

CUORE stays the tool used **before** wiTECH, which keeps the expensive tool for the work only it can do.

## Principles that do not change at scale

- **Protect the car.** Nothing is written without a documented or wiTECH-observed source, a dry run, typed consent and read-back. Recording is listen-only. See Safety Rules (wiki: Safety-Rules).
- **Evidence, not opinion.** Conclusions cite readings; outside facts are labelled.
- **Low-cost hardware.** The same USB adapter and bypass cables MES users already own.
- **Exclusive.** For Alfa Romeo, Maserati and Ferrari technicians, at dealers and independent shops; not a consumer app.
- **Manufacturer data stays licensed.** Service information is cited, not republished, unless a re-publishing agreement allows it.

## Where CUORE stands (2026-10-30)

| Area | Status |
|---|---|
| Functions a technician uses in MES or AlfaOBD | 98 tracked on the parity board: 32 done, 13 need one car session, 49 need manufacturer documents, 4 await a decision |
| Diagnosis, evidence, proof of repair, bulletin links | Working on the reference car; ahead of MES and AlfaOBD |
| Write procedures | 15 defined, none runnable: waiting for documents or wiTECH recordings |
| wiTECH recording (listen-only) and draft procedures | Built 2026-10-30 |
| Low-cost hardware | Proven on the vLinker FS USB adapter (STN1170) with the blue A5 and grey A6 bypass cables; adapter check page built |
| Coming from MES | Migration page built: same adapter and port, MES logs imported, MES-to-CUORE function map |
| Vehicles | Stelvio 949 in depth; Giulia 952 partly in data |
| Deployment | One Windows PC, single local login |

## Phase 0: foundations (now)

- Written authorization and scope from Stellantis, referenced in the repository.
- Service-information access: TechAuthority (North America) and stellantisiop.com (Europe), with terms confirmed for development use.
- Requests to Stellantis engineering: the module diagnostic specification (data identifiers, routines, security access, configuration map) and, for secured functions, the unlock algorithm or authenticated access.
- Source code and wiki moved to private hosting before any shop receives CUORE.

**Exit:** the written authorization is on file, both portals are accessible, and the code is private.

## Phase 1: complete the reference car (Stelvio 949)

- One read-only car session runs the 13-step Bench plan, closing the 13 "car session" rows.
- Service information fills the procedure files, the DTC test steps, wiring, locations and fuse maps.
- Dealer sessions with wiTECH: record the functions in order (oil and service reset, battery registration, paddle-shifter market with PROXI alignment, key learning last). Flashing is never recorded.
- First CUORE writes are made at the dealer with wiTECH ready to restore, starting with the oil service reset.
- Each function is proven side by side: same codes and values as MES; for writes, read-back plus a confirming wiTECH read.

**Exit:** every parity row a technician uses is done, with a recorded test on the car.

## Phase 2: pilot (one dealer, one independent shop)

- An installer and an update channel; every shop shows the CUORE version it runs.
- Accounts and roles: dealer technician, independent technician, shop lead; each shop's data kept separate.
- Training per screen (short, in the tool) and a support channel.
- Results measured from the start: first-time-fix rate, comebacks within 30 days, time to diagnosis, and wiTECH sessions avoided. MES and AlfaOBD jobs at the same shops are the baseline.
- Feedback from the dealer mechanics who saw the 2026-10-28 demo, gathered screen by screen.

**Exit:** both shops use CUORE as their first tool for a full month, with results at or above the baseline.

## Phase 3: platform

- Giulia 952, then further Alfa Romeo models, added as data files, not code.
- Maserati and Ferrari versions: marque styling and data per brand.
- Markets: units and language per market; Canada and the US first, then Europe, where independent shops reach manufacturer information through stellantisiop.com.

**Exit:** a second model and a second marque pass the same parity board.

## Phase 4: network rollout

- North American dealers, then European dealers, then independent shops through the manufacturer's independent-operator channel.
- MES and AlfaOBD users move across on the hardware they own (adapter check and MES migration pages).
- A shop is "on the standard" when its technicians use CUORE first and MES or AlfaOBD are no longer needed for any function on the parity board.

## What CUORE offers mechanics, beyond replacing MES and AlfaOBD

Added 2026-10-30. These build on parts CUORE already has; the phase says when each enters the plan.

**Before the car arrives**

| Offer | What the technician gets | Built from | Phase |
|---|---|---|---|
| Arrive-ready job | From the owner's report and the VIN, the job opens before booking: likely causes, open recalls and bulletins, parts to have on the shelf, whether wiTECH or bypass cables are needed, a time estimate | Owner reports, bulletin layer, parts catalogue, wiTECH hand-off page (exist; to be joined up) | 2 |
| Recall and campaign check at booking | No car leaves with an open recall | Bulletin layer; recalls by VIN from Stellantis | 2 |
| Bay plan | Charger, cables, adapter check and dealer-only procedures known before the car rolls in | Adapter check page, Adjustments | 2 |

**At the car and after**

| Offer | Value | Phase |
|---|---|---|
| Visit-to-visit history | "Last time this code appeared…", readings compared across visits for the same VIN | 1 |
| Proof-of-repair report for the customer | Plain-language evidence and photos that the fault is gone: trust, and a bill the customer understands | 2 |
| Comeback watch | Flags the same code returning within 30 days, with a follow-up reminder; also the pilot's results measure | 2 |
| Warranty evidence pack | Readings, snapshots, tests and bulletins bundled for a warranty claim; fewer no-fault-found part returns | 2 |
| Pre-delivery and certified pre-owned inspection | One standard scan with configuration check, recall status and module health for every new and used Alfa Romeo | 3 |

**Looking forward**

1. **Field-quality early warning for engineering.** Pooled across shops, with consent and without customer details: "the 949 is starting to show this code with these readings; fixed by X in 8 of 10 cases". Engineering sees emerging failures before a bulletin exists. Phase 4.
2. **Predictive service.** Trends in battery health, misfire counters, overboost counts and brake wear recommend a part before it fails. Phase 3.
3. **Remote second opinion.** An Alfa Romeo specialist opens a technician's job from anywhere, using the new accounts and roles. Phase 2.
4. **Training from real jobs.** Every finished diagnosis becomes a teaching case for apprentices, as the Case Study: Stelvio EVAP (wiki: Case-Study-Stelvio-EVAP) does. Phase 3.
5. **Owner connection.** An owner or in-car app sends symptoms straight to the dealer's CUORE. Phase 4.

Recommended first: the arrive-ready job (daily value for technicians), the warranty evidence pack (saves the manufacturer money) and the field-quality early warning (the strongest reason for Stellantis to standardise on CUORE).

## Hardware standard

| Item | Status |
|---|---|
| vLinker FS USB (STN1170) | Tested on the reference car |
| Blue A5 cable (CAN-IHS) | Tested |
| Grey A6 cable (CAN-CH) | Tested |
| OBD Y-splitter for wiTECH recording | Supported, listen-only |
| OBDLink MX+, ELM327 clones | Not tested; the adapter check page reports what each can do |

Other adapters are added only after a recorded test. No adapter is endorsed by brand.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| Damaging a customer's or the demo car's module | Documented or wiTECH-observed sources only; dry run, consent, read-back; listen-only recording; first writes at a dealer with wiTECH present |
| Secured functions (security access) | Unlock algorithm or authenticated access from Stellantis; until then those functions hand off to wiTECH |
| Secure Gateway on later model years | The manufacturer's authenticated diagnostic access |
| Licensing of service information | Cite rather than republish; a re-publishing agreement for anything shipped inside CUORE |
| Support load as shops join | Pilot first; training in the tool; feedback loop per screen |
| Results not better than MES and AlfaOBD | Measured from the pilot on; rollout waits for the numbers |

## What CUORE needs from Stellantis

1. Written authorization and scope.
2. Service-information access (TechAuthority, stellantisiop.com) and its terms of use.
3. The module diagnostic specification per platform, with the configuration (PROXI) map.
4. Security access for secured functions: the algorithm or authenticated access.
5. Permission and dealer time to record wiTECH on the demo car.
6. A pilot dealer and a pilot independent shop.
7. The same package for the Maserati and Ferrari models in scope.

Related: MES Parity Plan (wiki: MES-Parity-Plan), AlfaOBD Gap (wiki: AlfaOBD-Gap), Hardware and Cables (wiki: Hardware-and-Cables), Roadmap (wiki).
