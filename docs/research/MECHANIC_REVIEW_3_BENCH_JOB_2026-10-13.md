# CUORE — E2E re-test #3: Bench + Job, real browser walk

**Tested:** `/v/ZASFAKPN5J7B88115` (Bench) and `/v/ZASFAKPN5J7B88115/job` steps 1–12, Stelvio 2.0T,
EVAP P0440/P0455/P0456, headless Edge at 768×1024 (key screens repeated at 400×800), on 2026-10-13.
Fresh `CUORE_STATE_DIR` per run, own uvicorn server, own Edge profile — never the live `:5000`
server. One Edge instance, one tab, 8 screenshots.

**Flow tested (real browser interactions, not raw POSTs):** Bench → click into Job → step 5 →
step 6 record a **Fail** smoke test with a value (0.5 psi) *before* any hypothesis exists → step 7
add a hypothesis via the form, arriving with `?system=evap&codes=P0440` (as if clicked from a
system page) → attach a code as evidence → try **Confirmed** too early → go back to step 6 and
re-record the same test, now linked to the hypothesis → **Supported** → **Confirm** via the modal
→ Next → step 8 (plan) → step 10 (verify, blocker shown) → step 12 (release).

Every mutating action was a real `.click()` on the actual control (radio buttons, submit buttons,
the dialog's Save/Confirm), not a direct API call — the one exception is opening the case itself
(`POST /v/{vin}/job/open`, step 1 intake), seeded the same way `check_job_ux.py` already does,
since step 1 itself isn't in this review's scope.

## Overall

Run 2's fixes mostly hold under a real click-through, including under a deliberately awkward but
realistic ordering (test recorded before the hypothesis that explains it existed). No 500s anywhere
in the whole walk, no stray navigation, no reused title wording. The new finding worth the most
attention: the step-6 "Record result" sheet gets its hypothesis list from an async fetch that can
still be in flight when a tech opens the sheet, and when it loses that race the hypothesis dropdown
is silently empty — a Fail result gets saved and shown as saved, but it's never linked to anything,
and nothing on screen says so. Reproduced twice under the same timing; it is not a contrived edge
case.

---

## Results against run 2's R1–R8

| # | Item | Status | Notes |
|---|---|---|---|
| R1 | Header/bottom bar contradiction | ✅ Fixed, DOM-confirmed | Header carries only the step title, the "Job is at step N →" chip, and Steps ▾ — no back/next. Live-measured: exactly one `.btn.primary` in the step-nav on steps 5, 8, 10 (`Next: …`). **New wrinkle (N3 below):** app-wide, that one primary button renders visually identical to every secondary button — see N3. |
| R2 | "Job is at step N" doesn't move forward | ⚠️ Still reads wrong in practice | The chip read **"Job is at step 1"** through the entire walk, including after the hypothesis was fully confirmed with a real linked Fail test. Root cause traced to `flow_bridge.py`: step 1 requires an open *visit*, which `/v/{vin}/job/open` (the same seed `check_job_ux.py`'s own regression test uses) never creates — so `first_not_done` pins at 1 regardless of steps 5–7's real progress. The repo's own regression check only asserts `current != 7`, which is still true at `current == 1`, so it doesn't catch this. See N5. |
| R3 | Row stale after Save result | ✅ Mostly fixed, live-confirmed | Saving a Fail result updated the row in place with no reload: chip read "Fail · 0.5psi", `aria-pressed="true"`, `aria-label="Mark Run a smoke test to localise the leak not done"`. **But** the step-6 "N/M" counter (a second, separate async fetch) was still reading "Not started 0/22" in the same post-save window in one of two runs — see N2. |
| R4 | Next test doesn't move on after a result | ✅ Fixed (re-render on navigation) | Each `?step=N` is a full server render, not a client-side tab; after the relink + confirm, a fresh load of step 7 showed the confirm-reason collapse from the full "needs a test result" sentence down to just "Mark supported first." — `_display_next_test` correctly stopped returning the stale literal text once real test evidence existed. |
| R5 | Pass/Fail meaning unclear | ✅ Fixed, screenshot-confirmed | Result sheet reads "FAIL — LEAK/SMOKE FOUND" / "PASS — NO LEAK", Reason is marked (required) for non-pass, FOR/AGAINST auto-set to FOR the moment Fail was picked, 44px+ radio rows. No spec line shown for this row — correct, since this fixture's own row text carries no embedded number to show. |
| R6 | Stepper layout | ✅ Fixed | One row of 4 phase captions, current-step box highlighted, no horizontal page overflow at 400px (`scrollWidth == clientWidth == 400`), content starts well within the viewport. |
| R7 | Confirm modal too thin | ✅ Fixed | DOM-confirmed: the promoted `<dialog>` carried exactly "Cancel" / "Tap again to confirm", `open: true`; the server-rendered panel underneath it includes the hypothesis title, evidence lists, likelihood and any blocker (unchanged from job.html, confirmed by reading the template). Confirm stayed `disabled` with the tooltip "Mark supported first…" the whole time status was `open`, and only enabled once Supported — matches R7's "also" item. |
| R8 | Small items | ✅ Fixed | "Undo" button present on the status-change toast (seen in-flow); "Updated: Today 15:30" (not raw ISO); evidence chip read "P0440-00 freeze frame" (sentence case, mono only on the code); step 8 no longer references "step 7 Would buy next time"; vehicle name reads "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir" everywhere, never "(unnamed vehicle)". |

---

## New findings

### N1 (P1). The step-6 result sheet's hypothesis dropdown can silently open empty
**Seen:** Reproduced twice at the same ~1.8s post-navigation delay: once the dropdown correctly
pre-selected the hypothesis via its `next_test` match, once it opened with **only** the "Choose a
hypothesis…" placeholder — zero hypothesis options at all. `job.js`'s `enhanceResultSheet()` fetches
`/api/vehicles/{vin}/job` exactly once, at page-parse time, into a closure variable; `buildSheet()`
reads whatever that variable holds *at the moment the tech clicks "Record result,"* with no loading
state, no disabling of Save, and no retry. On the heavier EVAP dossier page this fetch can still be
in flight a full 1–2 seconds after the page looks interactive (the same caching/warm-up cost
`check_bench.py` already documents for this fixture). When it loses the race: the tech picks Fail,
enters 0.5 psi and a reason, taps Save, gets a "Saved." toast and a Fail chip on the row — indistinguishable
from a correctly linked save — but `hypothesis_id` posts as empty, so the result is never evidence for
anything, and the Confirm gate (the one correctly-enforced control from R1/R7) silently has nothing
to work with.
**Fix:** Fetch the hypothesis list when the sheet is *opened* (or re-fetch on open if stale), not
once at page load; disable Save (or show a spinner) until that fetch resolves.
**Accept when:** Opening "Record result" within 0ms of the row existing in the DOM either already has
the hypothesis list, or visibly waits for it — never silently offers only the empty placeholder while
Save stays clickable.

### N2 (P2, same root cause as N1). The step-6 counter can lag the row it sits above
**Seen:** In one run, immediately after the Fail chip appeared on the row (R3, confirmed working),
`.step6-status` still read "Not started 0/22" — a visible contradiction one scroll-length apart on
the same screen: the row says done, the header above it says nothing has started. `refreshCounters()`
is a second async fetch chained after the save, also with no loading indicator.
**Fix:** Either await both fetches before declaring the save complete, or show a brief "updating…"
state on the counter until it does.

### N3 (P2). The one primary button R1 restored is visually invisible
**Seen:** `cuore.css` (~line 1178) deliberately flattens every `.btn.primary` / `.btn-verdict.primary`
outside the sticky flow-bar's own "Suggested next" link to the same transparent-outline style as a
plain `.btn` — the comment there explains this is intentional ("one filled action... everything else
outline"). Confirmed in the result-sheet screenshot: "Cancel" and "Save result" render pixel-identical
except for an invisible class difference. The step-nav's lone `.btn.primary` Next button is correctly
alone in the DOM (R1 is real at the markup level) but on screen it looks exactly like Back, Cancel, Do
it now, and every status button. This isn't new damage from this pass — it's a global design choice —
but it quietly undoes the "a tech can tell the one thing to tap" goal R1 was written to restore.
**Fix:** Either accept this as the design (then R1's accept line should stop talking about "the
primary button" and start talking about "the only forward-navigation link"), or give the step-nav's
Next/Confirm/Save a filled treatment the way `.flow-next` already gets one.

### N4 (P2). The confirm-gate reason doesn't distinguish "no evidence" from "evidence that doesn't count"
**Seen:** After attaching a P0440 freeze-frame chip as Evidence for (1), the reason line still read
flatly "Needs a passed/failed test result linked," unchanged from when there was 0 evidence of any
kind. Sitting directly under a visible "Evidence for (1)" chip, this reads as self-contradictory to
someone who doesn't already know code/freeze-frame evidence and test evidence are different kinds.
**Fix:** When non-test evidence exists but no test evidence does, say so explicitly: "1 piece of
evidence on file, but none of it is a pass/fail test result yet."

### N5 (P2). R2's own regression check can't tell step-stuck-at-1 from step-moved-to-8
**Seen:** `check_job_ux.py`'s R2 assertion is `flow_after.get("current", 7) != 7` — true whether the
chip reads 2 or 8. In this run it was true because the chip was stuck at **1** (see R2 above), which
the existing check would wave through as a pass.
**Fix:** Tighten that assertion to the stated accept line ("the chip reads step 8"), or seed a visit
alongside the job so step 1 can actually complete, matching how a real intake works.

### N6 (P2). Touch targets: the shared top-nav bar dominates every "under 44px" count
**Seen (measured, `getBoundingClientRect` over every button/link/input on each screen):**

| Screen | Controls under 44px | Total |
|---|---|---|
| Bench @768 | 22 | 59 (37%) |
| Step 5 @768 | 43 | 77 (56%) |
| Step 7 (initial) @768 | 30 | 74 (41%) |
| Step 7 @400 | 36 | 90 (40%) |
| Step 12 @768 | 64 | 96 (67%) |

Every example captured (Start/Vehicles/Modules/Recordings/Logs/Live link/Coverage/Tools, 20–40px
tall) is the shared header nav from `base.html`/`_vbar.html`, present identically on every screen —
not job-page markup. `job.css`'s own touch-target fixes (44/48px on hyp-status buttons, result
radios, step-nav) are real and hold up, but they can never move this number because the dominant
offender lives outside `.job-page`.
**Fix:** belongs in the shared nav chrome, not `job.css`.

### N7 (P3). Sub-12px text is also mostly shared chrome, plus one real job-page source
**Seen:** Under-12px counts: Bench 17/140 (12%), step 5 18/202 (9%), step 7 19/211 (9%) — almost
all the header/footer chrome (`bench-state-badge` chips at 10px, "profile"/vin-tail/km at
10.5–11.5px, footer "CUORE 0.1.0" at 11px). One real job-page source, though: `cuore.css` sets a
blanket `label { font-size: 11px; }` (line 370), which is why step 7's own "Hypothesis"/"System"/
"Linked codes"/"Likelihood"/"Next test" field labels measured at 11px — not a job-page-only
redesign leftover, a one-line global rule affecting every form label app-wide.
**Fix:** bump the global `label` rule to 12px.

### N8 (P3). Free-text "evidence" renders identically to structured evidence
**Seen:** The evidence picker's free-text `label` input lets a tech type anything (e.g. "looks
worn") and it becomes an "Evidence for" chip styled exactly like a real P0440 freeze-frame citation,
with no visual marker that one is sourced from the car's own data and the other is typed. It cannot
bypass the Confirm gate (confirmed: the gate only counts `kind=="test"` pass/fail evidence), which
is the property that actually matters — but the evidence *count* shown on the card and in the
confirm modal doesn't distinguish them, so a skim could read more support than exists.
**Fix:** a small "manual" tag on free-text evidence chips, distinct from code/freeze-frame/test chips.

---

## What held up clean (said plainly)

- **No 500s** anywhere in the whole walk (seed, Bench, all 8 job-step loads, evidence attach, 4
  status transitions, the confirm modal, Next). The only non-200s were 404s for missing decorative
  brand assets (`logo.svg`, `multiair.jpg`, `favicon.ico`) — cosmetic, unrelated to any of this.
- **No auto-navigation.** Every mutating POST (add hypothesis, add evidence, all 4 status changes,
  the two result-sheet saves) landed back on the exact step it was invoked from. The only real
  navigation was the one a human actually triggers (Bench → Job, step-nav Next).
- **No text that orders instead of suggests.** Button/label wording throughout ("Record result",
  "Add a hypothesis", "Tap again to confirm", disabled-button tooltips) reads as explaining a gate,
  not commanding the tech.
- R3's row update, R5's result-sheet wording, R6's stepper, R7's modal content and gating, and R8's
  whole list are genuinely fixed, not just "better."

---

## Regression tests to add

1. **N1 (the load-bearing one):** open the real app, navigate to step 6, and click "Record result"
   on a row as close to page-load as the test harness can manage (0–200ms after the row exists in
   the DOM, before any `setTimeout`). Assert the hypothesis `<select>` either already contains the
   job's open hypotheses, or the sheet visibly shows a loading/disabled state rather than only the
   empty placeholder with Save still clickable. This is the one `check_job_ux.py` doesn't cover today
   because it drives the backend directly rather than racing the real page's own async fetch.
2. **N2:** after Save result, assert `.step6-status`'s text updates to the new N/M *before* the
   function that handles the save returns control to the caller (or poll it with a tight timeout and
   fail if it's still stale after, say, 2s) — same shape of check as #1, different element.
3. **N5:** tighten `check_job_ux.py`'s existing line
   `check("the job progress chip moves forward off step 7 once it's resolved (R2)", flow_after.get("current", 7) != 7, ...)`
   to assert `flow_after.get("current") == 8` specifically (or seed a visit so step 1 can complete),
   so a chip stuck at 1 can't pass as "moved forward."

*Test data left on this VIN:* none — this run's server used a throwaway `CUORE_STATE_DIR`, never the
live `:5000` instance, so nothing needs cleanup on the real car record this time.
