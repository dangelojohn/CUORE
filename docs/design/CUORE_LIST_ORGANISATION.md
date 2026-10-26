# CUORE list organisation: the rules every list follows

**Date:** 2026-10-26. **Status:** design rules for owner review; the pages marked "today" in
the appendix are being changed to follow them.
**Why now:** on the Job page the mechanic said: *"Instead of a long list there needs to be
greater organization of data and the ability to sort and find similarities and identify how
long and an easy way to press a button to say fixed... easy finding active and important error
first."* The owner added: *"identify grouping that can be opened with a small rotate arrow for
each grouping"* and *"priority and the most recent time matter more and need to be at the top."*
**Evidence behind it:** today's audit of 56 rendered pages (`list_audit.md`), the bay-tablet
spec (`docs/design/cuore-bay-tablet.html`), the shared CSS (`cuore/web/static/cuore.css`) and
CUORE's core directive: diagnose on evidence, prove the fix, learn for the next same-model car.

A list that makes the mechanic scroll to find the one thing that matters has failed, however
complete it is. Completeness is kept (everything is one tap away); the page leads with the answer.

---

## 0. Frame every page inherits (bay-tablet spec)

- One-line directing call at the top ("2 active faults, start with P0456"), then Go-to chips,
  then a "Why these?" fold. Lists sit below as grouped inset lists.
- Chips carry a label and a colour, never colour alone.
- Targets at least 44 px; text at least 16 px, only the seven `--fs-*` tokens; one column of
  about 820 px; light and dark both work.

---

## 1. Order: priority first, then most recent

The default sort is the right sort and needs no click. Other sorts (oldest, most codes, by
system, by duration) are options in a chip row, never a requirement.

**The fault priority ladder** (highest first):

1. Safety systems (airbag, ABS, steering, brakes) and anything that has the MIL on, while active
2. Permanent (cannot be cleared by a scan tool; only the car's own drive cycle removes it)
3. Active (present now)
4. Pending (seen once, not yet confirmed)
5. Stored / history (cleared or not present now; recurring ones before seen-once)
6. Verifying (repair done, waiting for evidence)
7. Proven fixed / resolved

Inside each rung: most recent event first. Ties after that: more occurrences first.

**Where it lives:** `cuore/data/fault_priority.json` (being built). Rung names, order, chip
colour and the safety-system list sit in that data file, not in templates. Every other list
that ranks things by importance (Inbox, Notes, Diagnosis, Timeline, Parts, Tests) **reuses it**
through one helper rather than inventing its own rule. Today the nearest equivalent is
`codes_call.group_rows` (Returned / Chronic / Seen once); the helper should wrap and extend it.

- Good: `/codes` shows worst-first groups with counts, "on this job" first, nine sort keys.
- Bad: `/notes` is newest-first only, so a one-line safety note sits under 40 PLAN notes;
  `/inbox` is insertion order, so questions about active codes can be at row 54.

Rule for non-fault lists: rank by the nearest fault rung they serve (a test that supports the
ACTIVE suspect outranks one for a stored code), then by recency.

---

## 2. Grouping: similar items share one fold

Group by what the mechanic would ask: shared cause, system, question key, kind of item.
Every group is one element:

```html
<details class="fold" open>
  <summary>Evaporative system <span class="count-badge">3 active, 4 stored</span></summary>
  ...rows...
</details>
```

- `details.fold` (in `cuore.css`) gives the small arrow that points right when closed and
  rotates down when open. Use it for every grouping. `.card-details` is the same arrow on a
  bordered card; use it when the group is a card, `fold` when it is a plain section.
- The summary always says **label + count**, plus a status chip when one item dominates.
- **Open by default:** any group containing an active, permanent or important item.
  **Closed by default:** groups that are all resolved, history, or UNKNOWN.
- Groups are ordered by the highest rung they contain (section 1), then by newest event.
- Good: Inbox shows "Any battery work, jump start or aftermarket electrical recently? Asked on
  21 codes: B1029, B102E ..." once, with one answer box, instead of 21 boxes.
- Bad: 44 of 54 Inbox items are four questions, each repeated with its own box and buttons.

---

## 3. Fold repeats into one counted line

Near-identical rows become one row: text, count, date span, members on tap.

- Good: "Cleared 22 times, 06-07 to 10-24" (one line, tap for the dates).
- Good: "Too few events (37 codes)" in one fold on `/intermittent`, with code chips.
- Bad: 37 identical "too few events (1)" rows; 316 copies of the unverified-interchange
  warning on `/catalog/other`; 18 identical GREY lines on `/fuses`.

Implementation: one shared helper that normalises text (digits to `#`), groups, and returns
`{text, count, first, last, members}`. A warning that applies to the whole page or shop is
printed **once** in the header, not per row.

---

## 4. Time: every item shows age, last time, and duration

- **Age** next to every item, as a relative phrase: "2 d ago", "asked 13 d ago". The absolute
  stamp is the tooltip, not the text.
- **Most recent** time drives the order inside a rung (section 1).
- **Duration** where an item has a life: "present 61 d", "verifying 3 d", "never logged".
- One shared Jinja macro `age(ts)` for all pages (the audit found raw timestamps on Notes,
  Inbox, Scans, Timeline, Trends; `/codes` already has `first_seen_ago`).
- Bad: Inbox and Notes showing `2026-10-13T14:02:11Z`. Good: "13 d ago".

---

## 5. One-line rows that expand

A row is one line: the thing, its status chip, its age. Everything else is behind the row.

- Row line = rank or status chip + name + one key fact + age. It must fit one line at 820 px.
- Long text (notes, rationale, procedures, caveats) never shows in full by default: first
  160 characters, then tap to expand. Rows expand in place via `<details>`, no JS needed.
- Good: Diagnosis suspect line "#2 EVAP purge valve, High, 71, 4 for / 1 against", tap for the
  reasons. Bad: 19 suspects with 237 rationale lines all expanded.
- Good: `/` home clusters collapsed with count, status chip and next step in the summary.
- Bad: `/tests` renders all 50 tests with their forms (1.24 MB). Show "Do next" and fold the rest.

---

## 6. One-tap actions with undo, no typing

Greasy hands: every common action is one button, 44 px, no text box.

- "Fixed", "Rule out", "Confirmed", "Done today", "Ordered / Bought / Fitted", "Pin",
  "Log another occurrence", "Dismiss", "Answer for all".
- **Undo:** every action shows "Done. Undo" for the rest of the page's life and in the history.
  Undo is a retraction record, not a deletion.
- **"Fixed" is not "Proven fixed".** Pressing Fixed moves the item to **Verifying**: the repair
  is claimed, the proof is not. Only evidence moves it to **Proven fixed** (the code stays
  absent through the drive cycles and readiness monitors that should have set it again, or a
  test passes). This is the core directive applied to a button: prove the fix.
- Actions go through the **existing stores** (job, notes, feedback, maintenance, hypotheses),
  which are append-only; undo appends a retract. Pages do not keep private "done" flags, or
  two pages will disagree. Resolved, pinned and done states live in the same store as the Job
  fault board.
- Good model: `/tests` PASS / FAIL buttons. Bad: `/diagnosis` has no way to rule a suspect out.

---

## 7. Search and filter chips, working without JS

- Every list over about 15 items has a search box and filter chips **with counts**
  ("Active 3", "Stored 12", "Verifying 1").
- They work as plain GET parameters (`?q=evap&status=active`) so the page works with JS off,
  survives reload, and can be shared. Use the existing helper in `cuore/web/page_search.py`.
- JS may enhance (live filter) but must never be required.
- A chip with count 0 is shown dimmed, not removed, so the mechanic sees it was considered.
- Good: `/sensors` search plus status / system / zone filters. Bad: `/maintenance`, `/trends`,
  `/parts` have none.

---

## 8. Honesty

- **No invented numbers or percentages.** A score is shown only if the engine computed it from
  readings, with its inputs one tap away.
- **Unknown stays UNKNOWN.** UNKNOWN rows are folded into one counted group ("Never logged
  (N)", "UNKNOWN (58)") below confirmed rows and are never mixed into them or ranked as if known.
- **Outside facts are labelled** ("Mopar catalogue", "forum report", "TSB 18-030-17") and never
  shown as proof; conclusions cite CUORE readings.
- Empty is stated: "No data from 20 sources" as one counted line, not 20 empty rows.
- Never rank a "Proven fixed" without the evidence it rests on being reachable in one tap.

---

## 9. Performance

- Lists stay fast on a tablet over Wi-Fi: target under about 200 KB of HTML per page.
  `/notes` (160 KB), `/tests` (1.24 MB) and `/report` (102 details, 95 forms) are over.
- Builders are cached; expensive builds run in the background or on demand, not on every
  request. **No blocking work in request handlers** (no adapter contact, no big scans).
- Heavy detail (forms, long text, member lists) loads on expand or on the detail page,
  not in the first render. Forms for rows the mechanic cannot yet act on are not rendered.
- A cap with an honest link beats an endless page: "Top 8 active codes, see all 85 on Codes".

---

## Review checklist (use on every list page)

- [ ] Directing call at top says what to do first, in one line
- [ ] Default order follows the fault ladder, then newest; no click needed to find the top item
- [ ] Items are grouped; each group is `<details class="fold">` with label + count
- [ ] Groups with active or important items are open; resolved, history and UNKNOWN closed
- [ ] Repeats folded into one counted line with a date span; page-wide warnings printed once
- [ ] Every row shows age ("2 d ago") and, where relevant, duration ("present 61 d")
- [ ] Rows are one line; text over 160 characters is behind a tap
- [ ] Common actions are one 44 px tap with Undo; "Fixed" goes to Verifying, not Proven fixed
- [ ] Actions write through the existing append-only store; undo is a retract
- [ ] Search and filter chips with counts work as GET parameters with JS off
- [ ] No invented numbers; UNKNOWN is folded and separate; outside facts are labelled
- [ ] Text 16 px or more, `--fs-*` tokens only; works in light and dark at about 820 px
- [ ] Page HTML is small and renders from a cached builder; no blocking work in the handler

---

## Appendix: audited pages and what changes

Source: 2026-10-26 audit of 56 rendered pages of 92 routes (VIN ZASFAKPN5J7B88115, copy of
ProgramData). "Today" means the change is being made on 2026-10-26.

| Page | List size found | Change made or planned | Status |
|---|---|---|---|
| Job fault board + repair log | long flat lists | Priority ladder, fold groups, one-tap Fixed / Verifying (by others, see Job work) | Today |
| `/inbox` | 54 open; 44 are 4 questions | Group by question key; one answer box per group; age; sort chips; Answer / Dismiss all | Today |
| `/notes` | 43 notes, 100K chars, 160 KB | Truncate to 160 chars; group by target; search, tag, 7-day chips; pin and resolved; age | Today |
| `/diagnosis` | 19 suspects, 237 rationale lines | One line per suspect; expand on tap; fold repeated evidence; rule out / confirm | Today |
| `/intermittent` | 40 rows, 37 "too few events" | Show 3 pattern rows; fold 37 into one counted group; latest-event age | Today |
| `/trends` | 14 metrics, 101 rows, ~20 "no data" | Metrics with data first; fold "no data" into one line; show span | Today |
| `/tests` | 50 tests, 0 done, 1.24 MB | "Do next" first, rest folded; state chips; last-result age; lazy forms | Today |
| `/maintenance` | 84 li, all "never / UNKNOWN" | Order by due status; fold "Never logged (N)"; due-in; "Done today" | Today |
| `/dashboard` | ~85-row code table, 178K chars | Cap to top 8 active; "last seen N d ago"; link to Codes | Today |
| `/timeline` | 108 tr, 5 identical findings | Correlation once; fold identical findings; sort families by active count | Today |
| `/parts` | 107 tr, 58 UNKNOWN | Sort by confidence and job; fold UNKNOWN per group; Ordered / Bought / Fitted | Today |
| `/catalog/other` | 170 items, warning x316 | Warning once per shop header; search and group chips; sort by fitment confidence | Today |
| `/codes` | ~42 li in groups | Already good: worst-first groups, 9 sorts, search, "ago". Gap: one-tap resolved | Already good |
| `/sensors` | 5 attention / 10 never read / 22 OK / 2 unplaced | Already good: attention first, OK folded, filters, ages | Already good |
| `/fuses` | 354 details, 427 li | Already good: status filters, search, "For this job" first. Gap: 18 identical GREY lines | Already good |
| `/` vehicle home | 11 details, 12 cards | Already good: clusters collapsed with count, chip, next step | Already good |
| `/report` | 164 li, 102 details, 95 forms | Not scheduled; open_work steps repeat 3x | Later |
| `/scans` | 13+ scans | Not scheduled; code column repeats codes | Later |
| `/mods` | 89 li, 19 cards | Not scheduled; no sort or age | Later |
| `/mes-parameters` | 189 tr, 25 to capture | Not scheduled; to-do already first | Later |
| `/electrical` | 94 element panels, 298 details | Not scheduled; 94 identical inspect forms | Later |

**Cross-cutting pieces the audit asked for** (build once, reuse everywhere): the `age(ts)`
macro; the fold-repeats helper; the shared importance rule from `fault_priority.json`; one
store for resolved / pinned / done so every page agrees.
