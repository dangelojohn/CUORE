# Jobs, Hypotheses and Mechanic Steps

CUORE organises its work as **one job per visit**. A job is the unit that ties together what the driver said, what the car showed, what the mechanic thinks, what was done and whether it worked. The store is `mes/jobs.py`; the page is `/v/{vin}/job`, and the same data is available through MCP tools (`job_open`, `job_add_hypothesis`, ...).

## The flow

The flow bar mirrors a mechanic's day: complaint, evidence, codes, understanding, tests, hypotheses, plan, repair, verification, documentation, release, tools away, next car. The job page is a stepper over the same sequence.

| Part of a job | What it holds |
|---|---|
| **Complaint** | What the owner or driver reported, in their words, with the date. Stored as attested input. |
| **Evidence** | Links to observations (readings from the car), MES log lines and dealer-tool results entered by hand. Each link keeps its provenance. |
| **Hypotheses** | A claim about the cause, with a status, a likelihood, evidence for and against, and a next test. |
| **Actions** | Everything done: notes, tests, inspections, repairs, parts fitted, clears (recorded, with the codes present beforehand), verification. |
| **Verification** | The proof that a repair worked. See [[Evidence Model|Evidence-Model]]. |
| **Close** | Closing a job records a **case**. |

Job, note, symptom and feedback stores are append-only. A deletion is a recorded soft delete that can be undone, so the history of what was believed at each point stays readable.

## Open jobs, and which one is current

A car can have several open jobs. The vehicle page now lists **every open job** with its title, the number of live hypotheses, a SAFETY chip where one applies, and a marker on the one that is current. "Current" is chosen by rule (`jobs.open_jobs`, `jobs.current`):

1. a job with a live **SAFETY hypothesis** comes first (a hypothesis flagged `safety` that is not deleted, not refuted and not marked attested-resolved);
2. then the **most recently updated** job (latest of opening, hypothesis update or action);
3. then the newest opened, so the choice is deterministic.

On the reference car two jobs are open: the EVAP job, and the job **"Network and chassis codes (non-EVAP)"**, opened 2026-10-20 with one hypothesis per group, in the priority order brakes, network, driver-assistance camera, keyless hub, window ([[Code Reviews|Code-Reviews]]).

A hypothesis may carry two flags. **`safety`** marks a hypothesis about a safety system (the brake-code hypothesis is one). **`attested_resolved`** records that the owner states the cause was resolved; the SAFETY chip then reads "owner-attested resolved, confirm with ABS read" instead of disappearing, and the job stops outranking others for that hypothesis. Attested is not measured: only the confirming read ends the flag's purpose.

## Action dates

An action records *when it was written* (`at`) and may also carry **`event_date`**, when the thing it records actually happened (a repair done last month, entered today). The date shown for an action (`effective_date`) is, in order: the `event_date`; a date parsed from the text (a leading ISO date, a "REPAIR HISTORY, ..." entry, or "between A and B", which takes the later date and is marked uncertain); else the recording time. An `event_date` must be an ISO date. The job page shows the effective date (marked "approx." when uncertain), and the bulletin cross-reference uses it to decide whether a repair came before or after a read.

## Hypotheses

- A hypothesis states what is suspected and why. It can be added, edited, have evidence attached or removed, be deleted and be restored. Its status follows a guided path: `open`, `supported`, `confirmed`, with `refuted` allowed from any state; its likelihood is `low`, `med` or `high`. The job store enforces the path: jumping from `open` straight to `confirmed`, confirming with no passed or failed test evidence, or confirming with unresolved evidence against it is refused. A job itself is `open`, `verifying` or `closed`.
- Evidence references have a kind: code, freeze frame, actuator, live, inspection, symptom, note, media, dealer, bulletin, feedback, test or observation.
- Adding a hypothesis **checks for a similar existing one** (`.../hypotheses/similar`) and offers suggestions, so the same idea is not recorded twice.
- A hypothesis can be revised in place when new information retracts part of it. The old text is kept, labelled as retracted, with the date. Example: the EVAP case retracted an idea about a solenoid in the suspect part after outside literature said the part has none; the old text stays on the job. See [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]].
- Hypotheses are checked against the dependency graph of 25 vehicle systems, so a mechanic sees which systems sit upstream of a code. Family findings are built in: several EVAP codes are usually one fault, and three or more lost-communication codes are usually one power or bus event (supply and grounds first).

## Mechanic steps

For any hypothesis, `mechanic_plan_bridge` (`/api/jobs/{job_id}/hypotheses/{hyp_id}/plan`) turns the hypothesis plus the bulletin cross-reference into **ordered, numbered tasks**. Each task cites its source: a bulletin, the hypothesis text, a job action, or a dependency path. A button saves the plan as the hypothesis's next test. The plan lists tools and the expected result of each step so that the result can be recorded against the same step.

**ESIM steps.** When an EVAP hypothesis names the leak-detection module (ESIM), two component steps are inserted after the VIN and currency checks and before the flash and test steps, because orientation is the cheapest check:

| Step | What it says | Source label |
|---|---|---|
| **E9 / `esim_inspect`**: orientation against the service drawing | The part is gravity dependent and must sit vertical, in the position the drawing shows; where the canister is angled an adaptor is used. It can be fitted four ways and only one is correct. Free, about 10 minutes. | Outside literature, **not a reading from this car**: a parts-maker tech tip, a repair-database tip about a truck, a trade article |
| **E10 / `esim_test`**: back-probe the signal | Back-probe the signal wire (do not pierce it): about 5 V at rest; with gentle hand vacuum of about 1 inch of water the switch closes and the signal falls to about 0 V (closed switch about 0.5 to 2 ohm). **Never 12 V across the switch**; hand vacuum only, never shop air. Free, about 15 minutes with a meter. | Outside literature, as above |

Both steps say that this engine computer tracks **no code** for the switch circuit (the status-bit map of 2026-10-19), so only the meter check exercises it. They are marked done when a recorded inspection, test or repair action mentions the ESIM with orientation or back-probe-and-volts wording. The same E9 and E10 ids exist in the EVAP fault tree (ids E1 to E8 stay stable). Details are on [[ESIM Bench Test|ESIM-Bench-Test]].

Example of the shape (from the reference case): VIN checks that need no tools first; then the dealer tool's ECM flash tab; then drive until the monitor completes (with the fuel and soak conditions stated); then read in CUORE; then decide; then record every step with date, values and meaning before the next.

## Supporting records

- **Recorded clears and repairs.** A clear done in MES is picked up by the auto-sync and added as a dated action ([[MES Integration|MES-Integration]]). A repair is a recorded action; it is not proof until the verification step.
- **Tools panel.** `tools_kb_bridge` lists tools for the job and keeps usage reviews and the garage's tool inventory.
- **Cases.** A closed job becomes a case. `cases.match` ranks real past cases above seed data for a new car, and `cases.prefill` pre-fills a new job from the closest case. The aim is that the next car with the same fault starts where the last one finished.
- **Shop visits.** Intake, step timing and release (`shop_visits.jsonl`). Release records that the tools are put away.
- **Dealer results and notes.** Typed in by hand; stored as attested input.
- **Modifications.** A non-stock car is flagged so other pages do not assume factory configuration.

## What a job never does

A job never writes to the car. Coding and configuration are done in the mechanic's other tools from a **handoff card** and then recorded here. Hypotheses and notes are not measurements and never enter the evidence gate as measurements. See [[Safety Rules|Safety-Rules]].

Related: [[TSB Layer and Cross-Reference|TSB-Layer-and-Cross-Reference]], [[Guided Full Scan|Guided-Full-Scan]].
