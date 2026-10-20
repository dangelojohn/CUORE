# CUORE Bench — UX/UI improvement spec

Context: findings from a live walkthrough of the Bench page for vehicle `ZASFAKPN5J7B88115`
(Alfa Romeo Stelvio, EVAP job: P0440/P0455/P0456, repair unverified, fuel 93.73%), done in a
~716px-wide viewport (Chrome side panel open — same width class as a phone in the garage).
Each item states what was observed, then the change to make. Priorities: **P1** = blocked or
misleading, **P2** = slows the work, **P3** = polish.

---

## A. Session pickup / resume

1. **P1 — No resume summary.** Returning to the bench, state had to be reconstructed from the
   banner, the footer timestamps, and the dossier. Add a "Resume" card at the top of Bench:
   last scan time (relative, e.g. "last scan 2 h ago"), what changed since last visit, tasks
   done vs open ("1 of 3"), and the single recommended next action. The data already exists
   (banner "Meanwhile: …", footer "last scan 08 Oct 09:26") — it's just scattered.

2. **P2 — Timestamps buried.** "Latest: 04 Oct 11:16 … last scan 08 Oct 09:26" lives only in
   the dossier footer area. Surface scan staleness on Bench itself; stale data silently
   invalidates the whole checklist.

3. **P2 — Vehicle identity inconsistent across views.** Bench tab title: "Alfa Romeo Stelvio
   2.0 Turbo 16V MultiAir — Bench"; Dossier page: "(unnamed vehicle) — Dossier". Persist one
   display name per vehicle and use it in every view and in `<title>`.

## B. The checklist itself (Bench working view)

4. **P1 — Tasks have no procedure or pass/fail criteria.** Each task is a one-liner
   ("Check hose routing") plus a bare reference number (9100325, S2125000002) that links to
   nothing. The mechanic (or an assisting agent) must invent the procedure. Make each task
   expandable: steps, the referenced diagram/doc inline or linked, expected readings, and an
   explicit "what counts as pass" line.

5. **P1 — "Mark done" captures no outcome.** The only control is a bare checkbox/submit.
   For a job whose end state is an evidence gate, binary done/undone is lossy. On mark-done,
   prompt for an outcome: OK / fault found (+ one-line finding) / skipped (+ reason), with
   undo. Findings should feed the dossier History automatically.

6. **P2 — Massive repetition per task row.** All three tasks repeat the identical parts list
   (ESIM, 04861961AD, 68337662AC, 68400620A_/…) and the identical tools list. Show shared
   parts/tools once at job level; per task show only what that task uniquely needs.

7. **P2 — Unresolved "?" placeholders.** Every tool renders as "EVAP SMOKE MACHINE — ?",
   "LAPTOP RUNNING MULTIECUSCAN (MES) — ?". Whatever the "?" was meant to resolve to
   (availability? link?), resolve it or hide it — as shipped it reads as broken output.

8. **P2 — No task ordering, progress, or blocked states.** The banner says "Meanwhile:
   Inspect the recirculation-line quick-connect" but the list itself shows three equal rows.
   Encode the logic visibly: task 1 = READY (recommended), task 2 = BLOCKED (MES not
   running), verification = BLOCKED (fuel > 85%). Show "N of M done" for the job.

## C. Preconditions & readiness logic

9. **P1 — Tool preconditions discovered mid-task.** The KOEO actuator test needs MES; the
   dossier chip says `MES NOT_RUNNING`, but Bench never mentions it. Per task, show its
   preconditions with live status and a one-click path to fix (e.g. "Connect MES →
   Live link"). Don't let the user start a task whose tool is down without a warning.

10. **P2 — Fuel-level gate is static text.** "will not run above 85 % fuel (set at 93.73 %)"
    is good, but make it live: current fuel % from last scan, how much to burn (~litres/km)
    to enter the 15–85 % window, and auto-refresh when a new scan lands. Add a monitor
    readiness panel (which OBD monitors complete/incomplete) since that *is* the
    verification gate.

## D. Codes row

11. **P2 — DTC chips are dead ends.** P0456 / B1040 / P0455 / P0440 / C141B are plain
    colored chips: no tooltip, no link, unclear color semantics (why is P0440 amber and
    P0455 red?). Each chip should link to its code page and show on hover: one-line meaning,
    status (active / stale / cleared-unverified), and which open-work item addresses it.
    Document the color scale in a legend.

## E. Ask / correct widget

12. **P1 — The floating panel covers the content it's about.** "Ask / correct (this page)"
    floats bottom-right and overlapped task text and the codes row in every screenshot;
    expanded, it hides a third of the checklist. Make it a side drawer or bottom sheet that
    pushes (not covers) content, and collapse it to a small FAB by default.

13. **P2 — Page-level only, and unclear verbs.** Corrections apply to "this page", but the
    unit the user disputes is one fact (one part number, one task). Add per-element
    affordance ("flag this row"), pre-filling context. The five radios
    (CORRECT / ASK / CONFIRM / ADD INPUT / DISAGREE) overlap semantically — CORRECT vs
    DISAGREE vs ADD INPUT is a taxonomy, not a user model. Two or three verbs with
    descriptions would do.

## F. Dossier

14. **P2 — Truncation destroys information.** Blind-spot titles render as
    "HAS EACH EMISSIONS MON", "IS A PERMANENT (MODE $…" — all-caps + hard truncation with no
    tooltip. Wrap instead of truncating, use sentence case. Same for the header chips:
    "NEXT: UNDER…" and the vehicle name "(unn…" truncate at side-panel width.

15. **P3 — "Why" section collapsed to a bare "…".** An unlabeled ellipsis button hides the
    reasoning. Label it ("Why unverified?") and show the first line uncollapsed.

16. **P2 — Navigation inconsistency.** Dossier has a top tab bar (BENCH / JOB / CODES /
    SYSTEMS / REPORT / MORE…); Bench has only "Job" / "Full dossier" buttons at the bottom.
    One persistent tab bar across both views.

## G. Narrow-viewport layout

17. **P1 — Overlapping floating elements at ~716px.** The Ask/correct expander, the ?/✎ FAB,
    and (when Claude is driving) the "Stop Claude" pill all stack over the task list and
    each other in the bottom third. Reserve the bottom-right corner: one FAB, everything
    else in-flow. Test at 400–800px widths; this is a garage/phone tool.

## H. Accessibility & agent/API affordances

CUORE is operated by humans *and* by assisting agents (this walkthrough was one). Both
benefit from the same fixes:

18. **P1 — Checkboxes aren't checkboxes.** The visual ☐ is decoration; the real control is a
    button whose accessible name is just "Mark done" — three identical names, so neither a
    screen reader nor an agent can tell which task a button belongs to. Also, only 2
    "Mark done" buttons were exposed in the accessibility tree for 3 visible tasks —
    verify every row has one. Use a real `<input type=checkbox>` (or `aria-pressed` button)
    labelled with the task title, e.g. "Mark done: Check hose routing".

19. **P2 — Machine-readable state.** Add stable `data-task-id` / `data-state`
    (ready/blocked/done) attributes on task rows and a documented endpoint (the Developer
    API link exists — good) to mark a task done *with* an outcome note. Include job state in
    the page `<title>` ("Bench · 1/3 · UNVERIFIED").

20. **P3 — "? keys" shortcut appears broken.** Footer advertises "? keys" but pressing `?`
    opened nothing on the dossier page. Fix the overlay or remove the hint.

---

## Suggested order of attack

P1 first: 1 (resume card), 4 (task procedures), 5 (outcome capture), 9 (preconditions),
12 (widget overlap), 17 (layout), 18 (checkbox semantics). Then the P2 batch — 6, 7, 8, 10,
11 together reshape the task row, so do them as one change. P3 last.
