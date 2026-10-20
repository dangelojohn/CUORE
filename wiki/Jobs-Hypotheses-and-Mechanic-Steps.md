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

## Hypotheses

- A hypothesis states what is suspected and why. It can be added, edited, have evidence attached or removed, be deleted and be restored. Its status follows a guided path: `open`, `supported`, `confirmed`, with `refuted` allowed from any state; its likelihood is `low`, `med` or `high`. The job store enforces the path: jumping from `open` straight to `confirmed`, confirming with no passed or failed test evidence, or confirming with unresolved evidence against it is refused. A job itself is `open`, `verifying` or `closed`.
- Evidence references have a kind: code, freeze frame, actuator, live, inspection, symptom, note, media, dealer, bulletin, feedback, test or observation.
- Adding a hypothesis **checks for a similar existing one** (`.../hypotheses/similar`) and offers suggestions, so the same idea is not recorded twice.
- A hypothesis can be revised in place when new information retracts part of it. The old text is kept, labelled as retracted, with the date. Example: the EVAP case retracted an idea about a solenoid in the suspect part after outside literature said the part has none; the old text stays on the job. See [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]].
- Hypotheses are checked against the dependency graph of 25 vehicle systems, so a mechanic sees which systems sit upstream of a code. Family findings are built in: several EVAP codes are usually one fault, and three or more lost-communication codes are usually one power or bus event (supply and grounds first).

## Mechanic steps

For any hypothesis, `mechanic_plan_bridge` (`/api/jobs/{job_id}/hypotheses/{hyp_id}/plan`) turns the hypothesis plus the bulletin cross-reference into **ordered, numbered tasks**. Each task cites its source: a bulletin, the hypothesis text, a job action, or a dependency path. A button saves the plan as the hypothesis's next test. The plan lists tools and the expected result of each step so that the result can be recorded against the same step.

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
