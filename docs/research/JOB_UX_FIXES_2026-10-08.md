# CUORE — UX/UI fixes from E2E diagnosis test

**Tested:** `/v/ZASFAKPN5J7B88115/job`, Alfa Romeo Stelvio 2.0T, EVAP codes P0440/P0455/P0456, at a tablet-portrait width (~710 px), on 2026-10-08.
**Flow tested:** Step 5 Understand the fault → Step 6 Tests → Step 7 add a hypothesis by hand → set its status → Step 8.
**Overall:** The diagnostic content is very strong: sourced confidence, fault trees, the fuel-level gate on the EVAP monitor and tool alternatives. The problem is the workflow shell around it. It lets a tech confirm a root cause with zero evidence, and it moves them to the next step without telling them. For a tool that promises "high correctness," that's the main thing to fix.

Fixes are ordered by priority. Each one has a **Fix** and an **Accept when** line that Claude Code can implement and test against.

---

## P0 — Diagnostic correctness (these block the main promise)

### 1. You can confirm a hypothesis with zero evidence
**Seen:** I added "Cracked EVAP purge line…", tapped `confirmed` once, and it was saved. The card still showed *Evidence for: none yet*, all EVAP tests were 0/6, and the Bench page itself said "Cannot verify yet: fuel 93.73 %, EVAP monitor will not run." There was no warning and no confirm dialog.
**Fix (guided-diagnostics pattern):**
- Status should follow a set path: `open → supported → confirmed`, plus `refuted` from any state. You can't jump from `open` straight to `confirmed`.
- `confirmed` requires at least 1 linked *evidence-for* item that is a test result (not only a code or freeze frame) and 0 unresolved *evidence-against* items.
- If the rule isn't met, disable the button and show the reason inline, for example: "Needs a passed/failed test result linked. Next: Smoke test EVAP system."
- If the vehicle has an active blocker (such as the fuel window or a monitor that can't run), show it on the card as a warning chip.
- Confirming opens a modal that summarizes the evidence and asks the tech to tap again. Record who confirmed it and when.
**Accept when:** POSTing `confirmed` on a hypothesis with no linked test result returns 409 with a message, and the UI shows that message. The step 7 summary never says "a hypothesis confirmed" for an unproven hypothesis.

### 2. There's no way to attach evidence to a hypothesis
**Seen:** The manual hypothesis card only offers four status buttons. You can't add evidence, link a test, edit, or delete it. I couldn't remove my test hypothesis, so it's still on the case with status `open`.
**Fix:**
- Each card gets **+ Evidence for** / **+ Evidence against** controls. These open a picker of on-file items: DTCs, freeze frames, live readings, completed test rows from step 6, and a free-text observation.
- Add **Edit** and **Delete** (soft-delete with Undo), and an audit trail.
**Accept when:** A tech can link a step 6 test result to a hypothesis in 2 taps or fewer, and the link shows on both the test row and the hypothesis card.

### 3. Test rows only record "done", not a result
**Seen:** Step 6 rows are a single checkbox ("Mark not done"/done + timestamp). A smoke test that *found* a leak and one that found nothing are saved the same way.
**Fix (scan-tool test pattern):** Ticking a row opens a result sheet with:
- **Result:** Pass / Fail / Inconclusive / Not possible (with a reason)
- **Measured value + unit** when the test has a spec (with known-good band shown), plus an optional photo
- **Which hypothesis does this support or refute?** (pre-selected by system)
Only Fail/Pass results count as evidence for #1.
**Accept when:** Every completed test row stores `result`, and optionally `value`, `unit` and `hypothesis_id`, and shows a coloured result chip.

### 4. Step status marks steps "green" when nothing has been done
**Seen:** Step 6 was shown green ("inspection, actuator run, or live observation on file") while all checklists were 0/6, 0/3, 0/3, 0/2, 0/2 and 0/6. Step 5 turned green after a hypothesis was added on step 7.
**Fix:** Use three explicit states for every step: **Not started / In progress (n of m) / Complete**. Each state comes from real criteria, and the counts are shown in the stepper ("6 · Tests 0/22").
**Accept when:** With 0 tests done, step 6 shows "Not started 0/22" in a neutral (not green) colour.

### 5. The app moves to the next step on its own
**Seen:** Setting the status to `confirmed` jumped the whole job to Step 8 "Plan the repair". Ticking a test checkbox on Step 6 **navigated away from JOB to the BENCH tab** (`/v/…#open-work`).
**Fix:** An action should never change the screen or tab. After saving, stay in place, keep the scroll position, and show a toast with **Undo**. Only move forward when the tech taps the primary **Next** button.
**Accept when:** All form posts on `/job` redirect back to `/job?step=<same>#<anchor-of-the-row>`, and a toast confirms the save.

---

## P1 — Navigation and orientation

### 6. The sticky header shows the wrong step
**Seen:** At `?step=7`, the header read "Step 5 of 12: Understand the fault". At `?step=6`, it read "Step 8 of 12: Plan the repair". The header follows the job's server-side "current step", not the step being viewed.
**Fix:** The header shows the step being viewed. If that's different from the job's progress, add a secondary chip: "Job is at step 8 →".

### 7. The primary button links to the current page
**Seen:** On step 5, the red **Review the code** button's href is `?step=5`, so tapping it does nothing.
**Fix:** The primary button is always **Next: <next step name> →**, or a specific action that moves the job forward. The secondary button is **← Back**. Use the same placement on every step: bottom-right on tablet, sticky bottom bar on mobile, as scan tools do.

### 8. The stepper isn't usable
**Seen:** The row `1 2 3 … 12` is bare numbers in about 11 px green text. Below it is a full list of all 12 steps, so every screen opens with a large amount of chrome before any content. The intro paragraph ("…nothing here is a second copy of the truth") is developer copy.
**Fix:**
- Replace both with one compact stepper: number + short label + state icon (done ✓ / in-progress ◐ / blocked ⚠ / todo ○). Group them into phases: **Intake (1–4) · Diagnose (5–7) · Repair (8–9) · Close-out (10–12)**.
- Collapse the step list into the `Steps ▾` menu.
- Remove the intro paragraph.
**Accept when:** The current step's content starts within the first 200 px below the sticky header.

### 9. The vehicle banner is unclear and inconsistent
**Seen:** The Job page says "(unnamed vehicle)" / "…B88115", while Bench says "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir". Raw enums such as `MES not_running` and `UNVERIFIED_REPAIR` show in the UI. The "Next: Understand the fault →" chip wraps across 4 lines.
**Fix:**
- One persistent vehicle banner, the same on every tab: **Year Make Model Engine · VIN last 8 · odometer · connection state** (`Scanner: disconnected`, using human labels).
- Map every enum to a display label.
- The "Next" chip becomes a single-line pill or is removed (it duplicates #7).

### 10. Step numbers referenced in content don't match
**Seen:** Step 8 says "Record your decision… in the step 7 'Would buy next time' review", but step 7 is Hypotheses.
**Fix:** Generate cross-references from the step registry (`step_link('review')`). Don't hard-code numbers.

---

## P1 — The hypothesis screen (step 7) layout

### 11. Suggestions crowd out the tech's own hypotheses, and there are duplicates
**Seen:** 16 suggested cards with dashed borders, most saying "Evidence for: none yet". Eight of them are copies of "Upstream check" with the same text. The tech's own form is at the very bottom, and the "Add a hypothesis" heading appears twice.
**Fix:**
- **Order:** Active hypotheses (ranked) → *Add hypothesis* (collapsed button at top) → Suggestions.
- Rank suggestions by the amount of evidence that supports them. Show only the top 3 and put the rest under "Show 13 more".
- Merge suggestions that share the same test into one card that lists the affected codes ("Upstream check: Network/CAN — B1029, B102E, B1040, B1176").
- Visually separate suggestions that have no evidence at all.
- Before adding a hypothesis, check whether a similar one already exists, for example "Similar to *EVAP: ESIM signal path* — merge?"

### 12. The manual hypothesis form is too small and not guided enough
**Seen:** There are 3 free-text inputs about 170 px wide; the Hypothesis input cuts off its own text. Validation is only the browser's native tooltip. System is free text, so values like "EVAP"/"evap"/"Evap system" will split the data.
**Fix:**
- Make the inputs full width.
- **System** is a select populated from the systems taxonomy the code cards already use.
- Add **Linked codes** (multi-select of open DTCs, pre-filled from system) and **Initial likelihood** (Low/Med/High).
- **Next test** offers suggestions from the fault tree.
- Show inline validation messages.

### 13. Hypothesis cards are missing key information
**Fix:** Each card shows a likelihood bar, counts of evidence for and against, the linked codes, the next test with a **Do it now →** deep-link to that row on step 6, and the last-updated time. Pin the leading hypothesis at the top.

---

## P2 — Readability and touch (shop-floor conditions)

### 14. Text is too small and too low-contrast for a shop floor
**Measured on step 7:**
- Body text is 13 px. Muted text in `#79848C` appears 111 times at 10–13 px, and some green labels are 10 px.
- Evidence chips are all-caps monospace green-on-dark (`P0455-00 FREEZE FRAME: ABOVE 85 %…`), which is hard to read quickly.

**Fix:**
- Body text at least 16 px, secondary text at least 14 px, nothing below 12 px.
- Muted text at least 4.5:1 contrast against the background (`#79848C` → about `#9AA4AC` or lighter).
- Evidence chips in sentence case with a code-ID prefix in monospace only.

### 15. Touch targets are too small
**Measured:** 28 of 83 interactive elements are smaller than 44 px. The top tabs are 40 px tall, the `MORE…` tab is 33 px, the `±` row buttons are about 17 px, and some full-width toggles are 21 px tall. A tech wearing gloves will miss them.
**Fix:** Make every interactive element at least 48×48 px, matching scan-tool tablets. The `±` "flag row" control needs a clear label or icon plus a tooltip, because right now it looks like an expand control.

### 16. Code cards use the wrong visual weight
**Seen:** The DTC is shown twice (a small `P0456` and then a huge 40 px `P0456`). System tags are underlined like links. The drivability symptom chips (`ROUGH_IDLE`, `HESITATION`…) use strikethrough to mean "not expected", which looks like a "deleted" or error state.
**Fix:**
- Show the DTC once in the header row with its status (Current/Pending/History), MIL state and confidence badge.
- Make system tags chips, not links.
- Symptom chips show "Expected ✓ / Not expected —" with a legend.
- Show raw source URLs as a "Sources (3)" disclosure.

### 17. The same message appears three times
**Seen:** The Bench page repeats the same "Cannot verify yet: fuel 93.73 %…" message 3 times (banner, card, heading).
**Fix:** Show it once as a **Blocker** banner, with an icon, a one-line action ("Burn fuel to 15–85 %, then run drive cycle"), and a "Why?" disclosure. Show the same blocker inside the Job flow on steps 7 and 10, because that's where it affects the decision.

---

## Suggested implementation order for Claude Code
1. #5 (no auto-navigation) + #6/#7 (header and Next button). These are small changes with a large effect.
2. #3 (test results) → #2 (evidence linking) → #1 (confirmation rules) → #4 (honest step status). #1 depends on #2 and #3.
3. #11–#13 step 7 layout.
4. #8–#10, then #14–#17 visual pass.

**Regression test to add (E2E):** Create a hypothesis → try to confirm it (expect blocked) → record a Fail smoke test linked to it → status moves to `supported` → confirm (with modal) → the page stays on step 7 → Next goes to step 8. Run it at 768×1024 and 1280×800.

*Test data note:* this run left one manual hypothesis on the VIN ("Cracked EVAP purge line at canister…", status reset to `open`). It can't be deleted from the UI (see #2). The step 6 checkbox I ticked was unticked again.
