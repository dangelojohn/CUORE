# Mechanic UX Review — CUORE Vehicle Dossier page
**Page reviewed:** `/v/ZASFAKPN5J7B88115` — Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir, Dossier tab
**Lens:** a working technician in a busy Alfa/Maserati/Ferrari specialist garage, gloves on, standing at the car, phone or wall tablet in hand. UX reference: professional diagnostic platforms (Autel MaxiSys / Launch X-431) — their workflow discipline, not their visuals.

---

## TOP RECOMMENDATIONS (implementation order for Claude Code)

These are ranked by impact-per-effort. Each has an acceptance criterion.

### R1 — Add a VERDICT card as the first element of the dossier
The page currently makes the mechanic *read prose* to learn the single most important fact: **the EVAP fault was cleared, not fixed, and verification is still pending.** A scanner shows a status; this page tells a story.

Build one card at the very top, before "Current picture":
- A status chip: `⬤ UNVERIFIED REPAIR` (amber) — states: `ACTIVE FAULTS` (red) / `UNVERIFIED REPAIR` (amber) / `VERIFIED CLEAN` (green) / `NO DATA` (grey).
- One sentence, max ~15 words: *"EVAP leak (P0455/P0440/P0456) cleared 29 Sep — monitors have not re-run. Not proof of repair."*
- Up to three action buttons, ≥48 px tall, full-width on narrow screens: **Verify repair** (runs/links `obd2.read_readiness`), **EVAP fault tree**, **Evidence gate**.
- The verdict is computed, not hand-written: latest-session DTC state + "cleared by scan X after last DTC session" + monitor/readiness status when available.

*Accepts when:* a mechanic who has never seen this car knows the state of the vehicle and their next action within 5 seconds, without scrolling.

### R2 — Collapse sticky chrome to one ≤56 px strip
Measured on the live page: the app header (96 px) + vehicle bar (191 px) = **287 px of sticky chrome in a 490 px viewport — 59 % of the screen never scrolls away.** On a phone at the car this is fatal.

- One sticky strip: `Stelvio 2.0TB MultiAir · …B88115 · 142,290 km · ⬤ MES down · ⬤ Live 0/3` + the section tab row. Everything else (log counts, date ranges, full VIN) scrolls away or lives behind a tap on the strip.
- App-level nav (Vehicles/Modules/Recordings/…) collapses to a menu button on narrow screens.

*Accepts when:* total sticky height ≤ ~110 px including the tab row; ≥75 % of a phone viewport shows content.

### R3 — Restructure the dossier from a scroll-document into collapsed summary cards
The page is ~9 screens of linear scroll. The mechanic must scroll past 17 "seen once" codes and 35 actuator-test rows to reach freeze frames and TSBs. Scanners never do this: they show a menu of dense summaries and drill in.

Every section renders as a card with a **one-line summary + count, collapsed by default** (except the verdict and open-work cards):

1. Verdict (R1) — always open
2. **Open work** — one card per family finding, always open (R4)
3. Blind spots — rendered as action chips (R8)
4. History — `Chronic 11 · Seen once 17` collapsed tables
5. Already attempted — grouped (R6)
6. Freeze frames — key-PID summary per family (R7)
7. Bulletins — deduplicated (R9)
8. Notes — with quick-add (R10)

Section state persists per vehicle (localStorage is fine). Add an in-page jump row (sticky with the tabs or a floating "sections" button) so nothing is more than 2 taps away.

*Accepts when:* the fully collapsed dossier fits in ~2 phone screens; any detail is reachable in ≤2 taps.

### R4 — Make family findings the primary object, styled — not raw JSON
The two `FAMILY FINDING` blocks are the smartest content on the page (EVAP = one fault not three; U-code storm = one power/bus event not twelve) **and they are printed as raw Python dicts** (`{'family': 'EVAP', 'codes': [...]}`). This single detail makes the tool look unfinished and buries the senior-tech insight.

Render each as a job card:
- Header: `EVAP — one system fault` + member code chips `P0440 P0455 P0456` (tap chip → code detail).
- The clinical ordering as a **numbered checklist with checkboxes** (recirc quick-connect → purge/vent KOEO actuation → hose routing per 9100325 → canister/ESIM per 9100471 → smoke test → SLVT/Mode $06 verify). Checked state persists per vehicle and is visible to the whole shop.
- Source refs (S2125000002, docs/research/EVAP_STELVIO.md) as small links, not inline prose.
- Same for the network family: supply (F82/BCM feeds) → connectors/grounds (XY201, G003A/B) → terminals, with its three TSB refs.

*Accepts when:* no raw dict/JSON renders anywhere; the EVAP card reads as a work plan a tech can tick off between interruptions.

### R5 — Fix the code tables: status chips, short dates, no horizontal clipping
On the live page the `DISTANCE` and `LAST SEEN` columns clip off-screen and every timestamp wraps to three lines (`2026-09-25` / `20:27:00`). Seconds-precision timestamps are noise at the car.

- Columns: `CODE | DESCRIPTION | STATUS | ×N | LAST SEEN | KM`. Drop `FIRST SEEN` from the table (it moves to the code detail view).
- `LAST SEEN` as `25 Sep` / `25 Sep '25` — tap for full timestamp. Never wrap.
- **STATUS chip per code**: `ACTIVE` (red), `CLEARED — UNVERIFIED` (amber), `STALE` (grey, not seen in N sessions). Right now an unresolved EVAP leak, a blocked window riser, and a dirty-camera code all look identical — the page has no triage signal at all.
- Group or badge by system (P/C/B/U or Engine/Chassis/Body/Network) so the engine work separates from the comfort noise.
- Row tap → code detail: description, first/last seen, freeze frame, matching TSBs, related family — one place per code (scanner "code → data" drill-down).
- Table head may stay sticky (already is) but must fit without horizontal scroll at 360 px.

*Accepts when:* at 360 px wide every column is visible, no cell wraps more than once, and the chronic table alone answers "what's actually wrong vs. what's noise".

### R6 — Collapse duplicate rows in "Already attempted"
Fifteen rows of `2026-09-15 21:18:00 · Evaporation control valve · COMPLETED` is log output, not information. Group by (operation, session): `Evaporation control valve — actuated ×8 · all completed · 15 Sep`. Failures sort first with their reason as a chip (`Request out of range`, `Engine running — interlock`). Keep the excellent interlock footnote ("key-on engine-off; 'Engine running' is an interlock, not a fault") attached to the relevant row, not floating below the table. Expandable to raw rows for audit.

*Accepts when:* the section is ≤10 rows for this vehicle and failed operations are visually first.

### R7 — Freeze frames: key PIDs first, flag out-of-window values
Each freeze frame dumps 28 PIDs with equal weight; `Clutch contact 2 — Released` sits level with the one value that decides the next step. For an EVAP code the mechanic cares about ~6 values — and this page is already smart enough to know which (it states the monitor window elsewhere: fuel 15–85 %).

- Summary row per code: fuel level, engine temp, odometer, speed/RPM, ambient/intake temp.
- **Annotate against the monitor window**: `⚠ Fuel 93.7 % — above 85 %: EVAP monitor could not run` on the P0455 frame. This turns a data dump into a diagnosis.
- Odometer delta vs. current ("set 360 km ago").
- Full 28-PID list behind an "All PIDs" expander, two-column on wide screens.

*Accepts when:* the P0455 frame shows the fuel-level flag without expanding anything.

### R8 — Blind spots become action buttons, not prose
Each blind spot already names its remedy (`obd2.read_readiness`, `obd2.read_permanent_dtcs`, `obd2.send_raw`, wiTECH request in fault-tree E8, fuel check). Render each as: question (bold, one line) → **action button** when a tool exists, with live enablement (`Read readiness` enabled when ELM327 on COM3 is up; greyed with "connect car" hint otherwise) → or a plain "dealer/wiTECH" tag when it doesn't. Keep the closing epistemic line — it's the soul of the tool — but one line, not a paragraph.

*Accepts when:* every answerable blind spot is answerable in one tap from this page.

### R9 — Deduplicate bulletins; group by bulletin, list covered codes
`18-030-17 REV. B` and `S2125000002` each render twice/thrice (once per code). Group by bulletin: title, the one-line action ("check recirc-line quick-connect before any parts"), chips for covered codes, superseded note, source+date. Order by relevance to the open family, not by code.

*Accepts when:* each bulletin appears once; the S2125000002 "check the quick-connect first" instruction also appears as step 1 of the EVAP checklist (R4) — same data, one source.

### R10 — Glove-ready ergonomics and workshop theme
Measured: nav links are 12.5 px text in 19 px-tall targets; body is 15 px; theme is low-contrast grey-on-white SaaS.

- All interactive targets ≥44 px (48 px for primary actions); ≥8 px gaps.
- Body ≥16 px; table numerics ≥14 px monospace (keep the mono — it's right).
- High contrast (WCAG AA minimum, aim AAA for status text); **dark theme** default-by-ambient or one-tap toggle — garages swing between glare and gloom, and every pro scanner ships dark.
- Status color system used *only* for status: red = active fault/failed, amber = unverified/caution, green = pass/complete, grey = stale/unknown. One accent (a deep Alfa rosso works for the marque) for primary actions — never for decoration. Restraint is what reads as "expensive"; the current pastel-badge look reads generic SaaS.
- Truncate log filenames (`FESLog_2610041116_Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir.txt` repeats full-width, thrice): show `FES log · 04 Oct 11:16`, filename on tap.
- Notes: floating quick-add button (bottom-right, thumb reach), target pre-selectable (vehicle / code / session), 44 px controls. A note nobody can add mid-job never gets added.

*Accepts when:* every action on the page passes a "work gloves on a 6-inch phone" test and the page is legible from 1 m on a wall tablet.

---

## 1. Mechanic UX assessment — what already works

This must be said clearly: **the content model is better than anything Autel or Launch ships.** The page encodes a senior technician's epistemics, which scanners do not:

- "Latest session is not the whole story" / "Clearing is not fixing" — explicitly separating *cleared* from *fixed*, and refusing to let a post-clear clean read masquerade as a verified repair. Most tools (and juniors) get burned by exactly this.
- Family findings — EVAP trio as one fault; the U-code storm as one power/bus event with a supply-first ordering. This is the correct diagnostic instinct, pre-computed.
- Blind spots — the tool states what its own data *cannot* prove (readiness, Mode $0A, Mode $06, calibration level) and names the instrument that can. Epistemic honesty is a professional feature; keep it.
- Already-attempted history with failure reasons, and the interlock explanation — stops a tech from repeating a colleague's dead ends.
- TSBs keyed to the car's actual open codes, with the "check the quick-connect before parts" and "check PCM calibration before condemning hardware" actions — exactly what prevents wasted canister replacements.
- Freeze frames that include fuel level — the one PID that decides whether the EVAP monitor can even run.
- Chronic vs. seen-once split, monospace numerics, bench/live provenance discipline, simulation-log exclusion notice.

The failure is not substance. It is that this substance is delivered as a **nine-screen scroll of prose and raw tables with no verdict, no triage colors, no actions, and chrome eating 59 % of a phone screen.** The knowledge is in the page; the page makes the mechanic excavate it.

## 2. What would frustrate or slow a mechanic down

- No at-a-glance state: the "what's wrong, what's next" answer requires reading three paragraph-cards in sequence.
- 287 px of sticky header on a ~490 px viewport; content peeks through a letterbox.
- Tables clip columns off-screen; timestamps wrap to three lines; seconds-precision everywhere.
- All 28 codes visually equal — no severity, no system grouping, no active/cleared/stale distinction. The *job* (EVAP) and the *noise* (window riser, dirty camera) have identical weight.
- 15 near-identical actuator rows; duplicate TSB cards; full log filenames repeated.
- Raw `{'family': ...}` dicts on screen.
- Freeze-frame PID dumps with the decisive value buried mid-list.
- Blind spots tell you the command to run instead of offering to run it.
- 19 px tap targets, 12.5 px nav text, low-contrast light theme — fails the gloves/glare test outright.
- Note-taking only at the very bottom of the longest page in the app.

## 3. What feels generic-SaaS rather than workshop tool

Grey-on-white cards, pastel badges, small quiet typography, equal-weight sections in a long scroll, content-as-article. A workshop tool is: status colors with meaning, dense fixed-grammar tables, big actions, persistent machine context, dark-capable, zero decorative variance. The *copy* already talks like a master tech; the *visual system* talks like a startup dashboard. Close that gap — in the direction of the copy.

## 4. Information hierarchy (recommended)

```
LEVEL 0 — sticky strip (≤56px + tabs)
  Vehicle · VIN tail · km · link status (MES / live buses)

LEVEL 1 — always visible on Dossier
  VERDICT: status chip · one sentence · ≤3 action buttons
  OPEN WORK: EVAP family card (checklist, 3 code chips)
             Network family card (checklist, code chips)

LEVEL 2 — one tap (collapsed cards with counts)
  Blind spots (action chips) · History (Chronic 11 / Once 17)
  Attempted (grouped) · Freeze frames (key PIDs)
  Bulletins (deduped) · Notes

LEVEL 3 — two taps (drill-down)
  Code detail (freeze frame + TSBs + sessions + family)
  Raw rows, full PID lists, full filenames, provenance detail
```

Demote: first-seen timestamps, log filenames, duplicate rows, the long provenance prose. Promote: repair-verification state, family checklists, out-of-window PID flags, runnable blind-spot actions.

## 5. Navigation / workflow

Map the page onto the real job loop — *car arrives → identify → scan/read → diagnose → repair → verify → document → next car*:

- **Arrive:** scan/VIN → this dossier. Verdict card answers "where did this car leave off."
- **Diagnose:** open-work checklist is the plan; code chips drill to evidence (freeze frame, TSB, history) and back — breadcrumb, never dead-end. The scanner pattern worth stealing wholesale: *you can always see where you are in the tree and always step back one level.*
- **Repair:** tick checklist steps; quick-note with photo on the step ("quick-connect O-ring split — replaced").
- **Verify:** the amber verdict *is* the open loop. "Verify repair" button runs readiness; page flips green only on monitor-pass or code-return answer. This state machine is the page's job between visits.
- **Document:** notes + checklist state already captured during the job become the RO story; add a print/share summary.

## 6. Missing functionality

- **Repair-verification tracker** (the big one): after a clear, show which monitors have/haven't re-run, fed by readiness reads; prompt the fuel-level precondition before the verification drive. The page *describes* this loop in prose today — it should *run* it.
- Job context: current complaint / RO / technician pin on the vehicle.
- Parts cross-reference from implicated components (purge valve, quick-connect p/n for this engine).
- Component location aids — a Stelvio recirc-line quick-connect photo/diagram next to checklist step 1.
- Session compare (pre/post-repair diff).
- Filter/search within history; filter noise families out of view.
- Print/export customer-facing summary.

## 7. How the redesigned page behaves during a real repair

Tech scans the VIN tag, phone in hand, gloves on. One amber banner: *"EVAP leak cleared 29 Sep — not verified."* Below it, the EVAP card with step 1 unchecked: *"Inspect recirculation-line quick-connect (S2125000002)."* They check the connector, find the split O-ring, tap the step done, dictate a one-line note. The card's next step offers the KOEO purge-valve actuation; the attempted-history note shows it ran clean ×8 on the 15th, so they skip to the smoke test. Before handing the car back they tap **Verify repair** — readiness says EVAP monitor not yet run, fuel at 93 % with the ⚠ flag — so the car waits for fuel to burn down, the verdict stays amber, and whoever picks the car up tomorrow sees exactly the same truth in five seconds. Nothing was typed, nothing was scrolled past, nothing was re-diagnosed.

## 8. Design brief (hand to any designer/developer)

> **CUORE Dossier** is the first screen a technician sees per vehicle. It must answer, in five seconds, gloves on, at the car: *what is wrong, what was already done, what do I do next, and can I trust the data.* Structure: one thin sticky vehicle strip; a computed verdict with status color and ≤3 big actions; always-open "open work" family cards whose checklists are the repair plan; everything else as collapsed, counted summary cards that drill down scanner-style with breadcrumbs. Tables use a fixed grammar (code · description · status chip · count · short date · km), never clip, never wrap timestamps. Status colors carry meaning only (red active / amber unverified / green verified / grey stale); one marque-appropriate accent for primary actions; dark theme; ≥44 px targets; ≥16 px body, mono numerics. Keep the tool's epistemic honesty (clearing ≠ fixing, blind spots, provenance) but compress it from paragraphs into states, chips, and one-line captions. The feel to hit: a high-end diagnostic workstation built by someone who has done the job — dense, calm, confident, expensive through restraint — never a consumer web app, and never a log viewer.

---
*Measured facts referenced above (from the live page, 480×490 viewport): sticky header 96 px + vehicle bar 191 px; body 15 px system-ui; nav links 12.5 px / 19 px tall; history tables overflow horizontally with DISTANCE clipped; FAMILY FINDING rendered as raw dict; 15 actuator rows at a single timestamp; 3 duplicate bulletin cards; ~110 CSS rules / 6 media queries.*
