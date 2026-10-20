# CUORE — E2E re-test #2: what changed and what's left

**Tested:** `/v/ZASFAKPN5J7B88115/job`, Stelvio 2.0T, EVAP P0440/P0455/P0456, at a tablet-portrait width (~710 px), on 2026-10-08.
**Flow tested:** Step 5 → Step 6, record a smoke-test result linked to a hypothesis → Step 7, try to confirm with no evidence (UI and direct POST) → open → supported → confirmed.
**Note:** The build changed *while I was testing*: the first load showed raw i18n keys, which were fixed a few minutes later. Everything below is checked against the latest build.

## Overall
The main problem from run 1 is fixed. A hypothesis can't be confirmed without a linked test result, and the server enforces `open → supported → confirmed`. Actions no longer move the tech to another screen. What's left is mostly about how clear and consistent the workflow is, plus two places where state on screen goes out of date.

---

## Results against the run 1 list

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Confirm needs evidence | ✅ Fixed | UI disables the button with a reason. A direct POST of `status=confirmed` with 0 evidence is rejected on the server. Open→confirmed is rejected. |
| 2 | Attach evidence / edit / delete | ✅ Fixed | `+ Evidence for/against`, Edit and Delete are all on the card. The result linked from step 6 shows up as evidence automatically. |
| 3 | Test result capture | ✅ Mostly | The result sheet has Pass/Fail/Inconclusive/Not possible, value + unit, reason and a hypothesis link. Remaining gaps are in R3–R5 below. |
| 4 | Honest step status | ✅ Fixed | Step 6 reads "0/22 test result(s) recorded", then 1/22. Step 7 reads "1/1 resolved beyond open". |
| 5 | No auto-navigation | ✅ Fixed | Saves stay on the same step and scroll to the right anchor, with a toast ("Saved.", "Status set to confirmed."). |
| 6 | Header shows the viewed step | ✅ Fixed | Adds a "Job is at step N →" chip. |
| 7 | Primary button = Next | ⚠️ Partial | The bottom bar is correct (← Back / Next: <step> →). The **header** buttons still follow the job's step, not the viewed one. See R1. |
| 8 | Stepper | ⚠️ Partial | Phases were added, but the labels overlap and the stepper scrolls sideways. Steps 1–6 are still listed above the content. See R6. |
| 9 | Vehicle banner / enums | ⚠️ Partial | "Scanner: not running" and "Unverified repair" now read well. The Job page still says **"(unnamed vehicle)"** (title and banner), while Bench says "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir". |
| 10 | Wrong step reference | ❌ Not fixed | Step 8 still says "Record your decision… in the step 7 'Would buy next time' review". |
| 11 | Suggestions | ✅ Fixed | Top 3 + "Show 4 more". The duplicate "Upstream check" cards are merged. "+ Add a hypothesis" is collapsed at the top. |
| 12 | Manual form | ✅ Fixed | System is a select (25 systems), with likelihood and linked codes. |
| 13 | Card info | ⚠️ Partial | It has evidence counts, Do it now →, Updated, and a likelihood bar. The **Next test is stale**: it still shows the smoke test after that test was recorded. See R4. |
| 14 | Font size / contrast | ⚠️ Partial | Muted grey is gone. On step 7 there are still **~80 text elements at 10–12 px**. |
| 15 | Touch targets ≥ 44 px | ❌ Not fixed | **45 of 98** controls are under 44 px. The result-sheet radios are about 13 px. |
| 16 | Code cards | ⚠️ Partial | The Expected ✓ / Not expected — legend is good. The DTC still appears twice (small + 40 px), and system tags are still underlined like links. |
| 17 | Blocker shown once | ✅ Fixed on step 7 | "Blocker: fuel out of window" banner with a "Why" link. |

---

## Remaining fixes (priority order)

### R1 (P1). The header and bottom bar contradict each other
**Seen on step 7:** The header shows `← Understand the fault` (step 5) and a red **Run tests** button (which goes to step 6). The bottom bar shows `← Back` (step 6) and **Next: Plan the repair →**. That's two different primary actions on one screen. On step 5, the header said **Confirm hypothesis**.
**Fix:** The header has *no* back/next buttons. Keep only the step title, the "Job is at step N →" chip and the Steps menu. The bottom bar is the only navigation.
**Accept when:** Each `/job?step=N` page has exactly one primary (red) button, and it links to step N+1.

### R2 (P1). "Job is at step 6" doesn't move forward
**Seen:** After recording the test result *and* confirming the hypothesis, the chip still says "Job is at step 6".
**Fix:** Work out job progress as the first step that isn't complete, using the same criteria as the step summaries. Recalculate it after every save.
**Accept when:** After a confirmed hypothesis plus at least 1 recorded result, the chip reads step 8.

### R3 (P1). The row doesn't update after Save result
**Seen:** After saving a **Fail** result, the row showed a red `Fail` chip, but the tick box stayed empty and the group counter stayed at `0/6`. Both only updated after a full reload (then ✓ and 1/6). The tick button also lost its accessible name ("Mark done" / title only, with empty text).
**Fix:** After saving the sheet, re-render the entire row and the group counter from the server response. Show the value on the row: `Fail · 0.5 psi`. Give the tick button `aria-label="Mark <row text> done"`.

### R4 (P1). Next test doesn't move on after a result
**Seen:** The card still shows "Next test: Smoke test EVAP system at 0.5 psi · Do it now →" after that test was recorded and linked.
**Fix:** Once the next test has a linked result, replace it with the next unresolved test from the fault tree (or "No further test — ready to confirm"). The status card should say so too.

### R5 (P1). What Pass/Fail means is unclear in the result sheet
**Seen:**
- For a smoke test, **FAIL** = leak found, which *supports* a leak hypothesis. Nothing explains this.
- The FOR/AGAINST radio defaults to FOR no matter which result is picked, so "Pass + FOR" can be saved.
- The hypothesis select defaults to "(none)" even when only one hypothesis is open.
- The sheet doesn't show the spec or known-good band. The reason field says "if FAIL", but a Fail with no reason is accepted.

**Fix:**
- Label each result with what it means for this test: "Fail — leak/smoke found", "Pass — no leak".
- Pre-select the hypothesis when exactly one is open, or the one the tech came from via **Do it now →**.
- Set FOR/AGAINST automatically from the result's meaning and let the tech override it, with a warning if it contradicts the result.
- Show the spec line under Measured value.
- Use radios at least 24 px with tap targets of 44 px or more.

### R6 (P2). Stepper layout
**Seen:** The phase labels run together ("DIAGNOSEREPAIRCLOSE-OUT") and the stepper scrolls sideways at 710 px. The step list 1–(N−1) still renders above the current step, so the content starts about 520 px down.
**Fix:** Use one row of 4 phase segments, with the current phase expanded to show its steps. Move the full list into the **Steps ▾** menu.
**Accept when:** There's no horizontal scroll at 710 px, and the current step heading is no more than 200 px below the sticky header.

### R7 (P2). Confirm modal is too thin
**Seen:** It only says "Evidence for: 1 · Evidence against: 0". It doesn't name the hypothesis or list the evidence, and it doesn't mention the active fuel blocker. The buttons are stacked and left-aligned.
**Fix:** Show the hypothesis title, the evidence list and any active blockers ("Repair cannot be verified until fuel is 15–85 %"). Put Cancel and **Confirm** side by side, with Confirm as the primary button. Record and display "Confirmed by <user> · <time>" on the card.
**Also:** The open → confirmed rule is enforced only *after* the modal (the error appears as a toast). Disable `confirmed` while the status is `open`, and give it a tooltip: "Mark supported first".

### R8 (P2). Small items still open
- Toasts don't have **Undo**. Add it at least for status changes and Delete.
- The "Updated" timestamp shows raw ISO (`2026-10-08T15:58:41`). Show it as "Today 15:58".
- Evidence chips are monospace. Use sentence case, with monospace only for codes.
- In the evidence picker, the first option reads "No evidence on file for this yet". Change it to "Choose evidence…".
- Fix #10 (the step-number reference) and #9 (vehicle name on Job).

---

## Regression test (passed this run, add to the suite)
Create a hypothesis → `confirmed` is disabled, and a direct POST is rejected → record a Fail smoke test linked to the hypothesis → evidence (1) appears on the card → open→confirmed is rejected → supported → confirm via modal → status is confirmed, the page stays on step 7, and step 7 summary reads 1/1.
**Add these assertions:** after save the row shows ✓ and the counter is 1/6 *without a reload* (R3). The Next test changes (R4). The job chip moves forward (R2).

*Test data left on this VIN:* the hypothesis "Cracked EVAP purge line at canister…" (now **confirmed**) and a **Fail 0.5 psi** smoke-test result on row `evap-5`. Delete both before using this car for real work. Delete is now available on the card.
