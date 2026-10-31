# Working rules

Each rule has its reason. Rules 1-12 are standing project rules; the design rules at the end keep the interface consistent.

## 1. Diagnose on evidence

Every conclusion rests on something CUORE captured or the mechanic observed, stored with a timestamp, source and confidence. Parts are not replaced on a hunch ("no parts cannon"); a part is listed for replacement only when a reading implicates it.

Why: the project exists so a model-specialist mechanic diagnoses on evidence, proves the repair, and the next car with the same fault starts where the last one finished. Core directive, recorded 2026-10-08 after drift toward shop management.

## 2. Readings-only conclusions; outside sources labelled

Diagnostic conclusions cite a reading CUORE itself captured (observation with timestamp). Statements reported by people, and outside facts (service literature, bulletins, catalogue part numbers), may be shown only labelled as such and never as proof. Certainty figures are given from readings alone, and a separate note says how they would shift if outside facts were admitted.

Why (2026-10-19): unverifiable statements and outside literature had been used in a way that looked like proof and was not. A challenged part row had no reading behind it.

## 3. Never clear codes without consent, and never as proof

Clearing is consent-gated per module: a person approves the exact call on the CUORE approve page (typing the phrase `CLEAR <MODULE>` there; the tool cannot approve for itself, see `docs/design/CONSENT_GATE.md`), the vehicle must read stationary, and the chassis bus needs an extra confirm. It reads and stores every code, snapshot and counter before the clear, reads back afterwards, and reports refusals instead of claiming success. A clear is never phrased as evidence of a repair. Do not clear before a full monitor run (EVAP) has completed, and do not rely on the check-engine lamp as the indicator of a fault or its repair; track the status bytes instead.

Why: a clear erases freeze frames and resets readiness, so an empty re-read proves nothing; repeated clears had destroyed evidence the diagnosis needed. Related commits: 3440054, 8dce38d (captures taken before anything can erase them), 0cdd74c.

## 4. No raw adapter scripts; confirmed bitrates only

All adapter contact goes through CUORE's audited session layer. No ad-hoc serial scripts against the adapter. A vehicle bus is never opened at any rate other than its confirmed one (CAN-C 500k, CAN-IHS 125k, CAN-CH 500k). No "guess the bitrate" sweeps. If a bus looks silent, suspect the monitor settings (STMA with ATCAF0, 11-bit route) before touching the rate. New adapter command sequences are bench-tested off the car first.

Why: on 2026-10-14 a script run outside CUORE listened on the chassis bus at the wrong rates; the cluster dropped brake, steering and airbag messages and warning lamps lit with a chime. Nothing outside CUORE is audited, so the event had to be reconstructed from file timestamps. Fix and rule: c57de05.

Second incident, same class: 2026-10-23 00:50:02 and 00:50:08 the owner pulled the blue A5 cable during a CAN-IHS session; `verify_bus()` heard nothing at 125k and then sent a functional `3E 00` at 125k onto the 500k CAN-C bus (CAN ERROR, no reply; bystander U-code check pending). Rule: on any cable route or non-500k bus, no transmit of any kind unless the passive listen in the same call heard at least 5 frames at the declared rate within the last 10 s; silence never triggers a send there. A pulled cable is auto-detected by a passive 500k listen and declared `none`. Every transmit decision is logged.

## 5. One program on the port

Only one program may hold the adapter's serial port at a time. CUORE is the adapter's single owner; the OBD MCP server is a thin client of it, and CUORE refuses to open the port while MES is connected.

Why: two programs on one port corrupt both conversations; MES also holds the port while connected, which had blocked live readiness and permanent-code reads. Commits: 96473d5 (MES interlock), 0039861 (one owner).

## 6. Verified how-to and forum links, from a data table, never invented

Every error code, fault family and service job is followed by "Others' experience": reputable video how-tos and direct forum threads, with title, source, date and what each covers. Links live in a data table keyed by code, family or job; each is verified reachable before saving and graded by reputation. A new entry is added whenever a new code or job is researched. Printed or PDF pages carry an "as of" stamp and sources; stale or unverified items are labelled, never silently presented.

Why: other mechanics' and owners' experience is among the most valuable information in a garage, and the mechanic acts on what CUORE shows, so it must be truthful and dated. The mechanic makes the decisions and the repairs; CUORE supplies the most recent and truthful information.

## 7. Bulletins are cross-referenced, not listed

Bulletins, recalls and campaigns are related to every DTC, every repair recorded, every hypothesis and the system-dependency layer, with an explicit reason per relation (explains, historical, same_system, dependent_system, candidate, already_applied, did_not_resolve, ruled_out_by_inspection, supports, weakens). New catalogue rows fill components, symptoms, implied repair and dependent systems from opened documents only. Suggested evidence is offered, never written automatically.

Why: a bulletin matters only in relation to this car's codes, what was already replaced, what is hypothesised and the systems upstream and downstream. A flat list (first version of the bulletin page, 0cdd74c) was not enough; the engine is 173dc9c.

## 8. Descriptive hypothesis-layer entries

Every job action, evidence item, hypothesis and note states: what was done and with which tool and route; when (absolute date-time); the numbers read (status bytes, counts, distance, monitor states); what it means for the hypothesis (supports, weakens or neutral, and why); what would confirm or refute it next. Several sentences, not a label.

Why: these entries are what a mechanic or the next session reads cold. A terse line loses the reasoning that makes the record evidence.

## 9. Search past records before asking again

At the start of any diagnosis follow-up, search the project's own records (notes, session transcripts, scan logs, the job ledger) for repairs, parts, tests and observations already reported. Record every reported repair or test with its date immediately. When asked for a conclusion, give one committed answer.

Why: re-asking for information already supplied wasted time and trust, and led to work (a bench test) built around parts that had already been replaced.

## 10. Scan sparingly: one complete guided scan per session

Do not keep re-probing the car. One complete guided scan per session (standard plug, then the blue A5 cable, then the grey A6 cable, counts as one), roughly ten scans over a whole diagnosis, each saved to the Scans log with its health report. Every scan reports "captured N of M" with a reason per gap.

Why: project-owner direction on 2026-10-13; it also reduces the risk of disturbing the car.

## 11. Test reads never become evidence

Observations record their stream, and only serial reads from a real car count as evidence. Test runs write to a throwaway state directory. Simulation-mode logs are excluded from code extraction.

Why: on 2026-09-26 scripted test reads and fake sessions had leaked into the real store and the evidence gate would have accepted them (9114102).

## 12. Read-only by default; writes are explicit and gated

The live-data poller is read-only. Coding and configuration writes are blocked on every module by service (157177d). Actuator tests need a person's approval on the approve page, are bounded in time, check the return to the ECU, and need the engine off. Vehicle modifications (for example paddle-shift) are a separate layer from diagnostics.

## 13. Save everything gathered (owner rule, 2026-10-29)

Every research pass keeps its raw material: fetched pages and PDFs, extracted text, search results, source URLs, owner statements, and a copy of the finished document. Save it the same day so it is available later. Vendor or licensed material and forum text go under C:/ProgramData/cuore/research/<topic>_<date>/ with a SOURCES_AND_FINDINGS.md listing each file and URL; vendor files, licensed material and forum text never enter this public repository. The repo holds the finished document, with citations, and a research log of sources and findings (docs/research/<TOPIC>_SOURCES_<date>.md) when it contains no licensed or sensitive material. Saving is not permission to act on the material: the write rules above still apply. First instance: C:/ProgramData/cuore/research/alfaobd_2026-10-29/ with docs/research/ALFAOBD_SOURCES_2026-10-29.md in the repo.

## Design rules (interface)

- CUORE is the mechanic's diagnostic assistant, not a manager or owner tool. It advises, records and remembers; it never blocks (the release step says "not verified" and records the decision).
- One car at a time, start to finish. No multi-car day board.
- The Job page is the single scrolling workspace in diagnostic order; one step per screen; every section opens from a headline with a count.
- Single column at every width. No side-by-side panels.
- Pictograms carry meaning, words are secondary; priorities marked P1/P2/P3.
- Marque look: dark, calm, true black, large quiet type with light display weight (300), one accent used only for the primary action. Marque specifics live in data or config, not code. Typefaces (owner decision 2026-10-29, after the manufacturers' permission): each marque has its own display and numerals faces carried by the --display and --numerals tokens, self-hosted under static/fonts; open-licence stand-ins until the brand packages arrive, then the manufacturers' own files with their licences. Sizes and weights keep the type scale; nothing is fabricated or copied from the web.
- CSS is edited incrementally. No consolidation pass without side-by-side screenshot approval. Never write a literal comment-closing marker inside a CSS comment (it silently dropped the whole variable block once, fixed in c50f90d).
- Offline-safe: no CDN assets; fonts are self-hosted files, never fetched at page load.
- Every EVAP-specific path has a general form for any code or family; EVAP is the worked example, not the scope.
- Owner-facing wording (report, handover) carries care and respect: the standard is the car returned driving as it should.
