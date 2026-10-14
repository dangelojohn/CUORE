# CUORE — E2E re-test #5: Scan wizard, Freeze-frame panel, Health, Scans list/diff, Job step 7 Mode 06, Messages/History

**Tested:** `ZASFAKPN5J7B88115` (the Stelvio), against a throwaway `CUORE_STATE_DIR` per
checkpoint, each seeded *only* with the real `2026-10-13` lines copied verbatim out of
`C:\ProgramData\cuore\observations.jsonl` (read-only source, never written to), on this review's
own uvicorn server with `cuore.live.ops` monkeypatched with the fakes from
`cuore/tests/check_fullscan.py` (so the wizard/freeze panel work with no real adapter). Never the
live `:5000` instance, never COM3. Headless Edge, one instance at a time (a fresh profile per
checkpoint), cleaned up via `cuore/tests/_edge_cleanup.py`'s own `kill_edge_profile`. Driven over
raw CDP (websockets), same posture as `cuore/tests/check_bench.py` -- real clicks on the actual
on-screen controls wherever the task called for a walk-through, not raw HTTP calls standing in for
them. Run as six independent, synchronous per-checkpoint scripts (`cp1_wizard.py` .. `cp6_messages.py`,
sharing `common.py`/`server_app.py`, all in this session's scratchpad -- not committed to the repo),
each with its own fresh server+browser+state dir, so a cut-off leaves this file current through the
last completed checkpoint and no single long-running process to kill mid-flight.

Checkpoints: (1) guided scan wizard, (2) Live board freeze-frame panel, (3) Health report,
(4) Scans list + diff, (5) Job step 7 Mode 06 evidence picker, (6) `/m/{vin}` Messages/History.
All six ran to completion; no checkpoint was skipped.

**Screenshot count: 9, one over this review's own 8-screenshot budget** (cp1: 1, cp2: 1, cp3: 2,
cp4: 2, cp5: 1, cp6: 2) — noted here rather than silently going over; every one was already taken
and used for a finding or a pass confirmation by the time the count was added up, so none was
discarded after the fact to force compliance.

## Checkpoint 1 — `/v/{vin}/scan` guided wizard
**Passed.** Full real-click walk (idle → Start → pause_blue → Skip → pause_grey → Skip →
remove_cable → Continue → summary), each transition a genuine DOM click on the actual on-screen
button (not a raw POST), confirmed by a reload-detecting wait (a same-URL `data-phase` swap can
otherwise race a naive `readyState` check — the harness's own first version falsely reported every
Skip/Continue as a no-op because of this, fixed before any findings below were taken). 20/20
measured checks passed; one screenshot (`shot_cp1_pause_blue.png`, 390×844).

- **Seen (DOM + screenshot):** idle shows the "Which cable for which module" reference block
  (`Blue A5` / `Grey A6` columns, confidence chips, module codes) — present and correct. Clicking
  Start moved `data-phase` to `pause_blue`; the pause card showed the big `BLUE A5 (CAN-IHS)`
  heading, the same cable-reference block still underneath (never dropped mid-flow, matching
  `check_cable_reference_rendered` in `cuore/tests/check_fullscan.py`), and the unlock list
  ("Climate control (TRW), AlfaConnect radio-nav / uConnect, Amplifier, …"). Skip → `pause_grey`
  (`GREY A6`/CAN-CH). Skip → `remove_cable` ("Remove the cable"). Continue (`cable_fitted=none`) →
  `data-phase="summary"`, page text contains "complete", and both an "Open in Scans" and a "Health
  report" link are present and point at the just-finished `scan_id`.
- **Measured (390×844, pause_blue screen):** every labelled `<button>`/`a.btn` on screen is
  ≥44×44px (Continue: 254×44px, the back-to-top FAB: 52×52px); smallest control text is the "Send"
  feedback-widget button at 13px — nothing under the 12px floor.
- **Seen (screenshot):** directly above the `BLUE A5 (CAN-IHS)` heading sits a plain solid-blue
  rectangle roughly full-width × 80px — the `.fscan-pictogram.fscan-pic-blue_a5` element. Its CSS
  (`web/static/fullscan.css`) is a flat `background: #2f6fed` (grey `#8a9099` for A6, the page rule
  colour for "none") — there is no actual pictogram/illustration despite the class name, and the
  element carries `aria-hidden="true"`, so it conveys nothing to assistive tech either. Not a safety
  issue (the heading text already says "BLUE A5"/"GREY A6" in words), but it is dead visual weight
  that promises a picture of the cable and delivers a colour swatch — see N1.

### N1 (P2). The wizard's "pictogram" is a plain colour block, not a picture
**Seen:** `web/templates/fullscan.html` renders `<div class="fscan-pictogram fscan-pic-{{ nxt.cable
}}" aria-hidden="true"></div>` on every pause screen; `web/static/fullscan.css` gives it nothing but
a flat background colour (blue/grey/rule-colour). A mechanic colour-deficient to blue/grey gets no
differentiation from this element at all (the redeeming fact is the heading text spells out
"BLUE A5"/"GREY A6", so it's not the only cue).
**Fix:** either replace it with a real connector/cable illustration (what "pictogram" implies), or
drop the empty block and give that vertical space back to content — right now it's ~80px of blank
colour for a screen that already said the cable name in text one line below.
**Accept when:** the pause screens either show a real pictogram or no longer carry an unused
decorative element sized that prominently.

No other issues found in this checkpoint: cable reference block never dropped across any phase,
summary links verified present, no dead ends.

## Checkpoint 2 — Live board freeze-frame panel
**Passed.** Real clicks throughout (`#ff-start`, `#ff-discard`, `#ff-start` again, `#ff-save`),
polled against actual DOM state since this panel is fetch-driven (no page reload) rather than a
full navigation. 21/21 checks passed; one screenshot (`shot_cp2_capture_done.png`, 390×844).

- **Start → Discard:** Start enabled the Save button once the (fake-adapter, near-instant)
  capture finished; status line read **"Capture complete — Not saved yet."**; the freeze-frame
  table rendered (`Freeze frame — P0440 (18DAF110) captured 2026-10-14T06:52:22 — read from the
  car`, one row per supported PID — generic `name_01`…`name_46`/`1.23`/`"u"` values, because this
  review's own fakes return placeholder names/units for every PID, not a real app defect). Discard
  cleared the panel back to idle (Discard and Save both hidden again) — confirmed the button
  actually works, not just that it's present.
- **Start → Save:** a second capture, Save produced **"Saved to the CUORE log — SCAN_2610140651"**
  plus a working **"open in Scans"** link (`/v/{vin}/scans/SCAN_2610140651`); followed for real —
  resolved to a live page carrying that scan id, not a dead link.
- **Seen (screenshot):** at the moment of capture, the page's one-per-session opening splash
  (`_intro.html` — a full-screen `position: fixed; z-index: 9999` overlay, label-wrapped so a tap
  anywhere on it dismisses it, ~2.2s fade) was still fading out, its ghost text ("CUORE / THE
  MECHANIC'S OWN RECORD OF THE CAR") visibly overlapping the freeze-frame table rows underneath —
  see N2. Button sizes on this panel read comfortably (Start/Discard/Save all full-height pill
  buttons, Save in the destructive-looking dark red seen elsewhere for primary actions).

### N2 (P2, traced from source — not reproduced as a missed tap). The opening splash can sit on top of the very first real tap of a session
**Seen (screenshot + source read):** `_intro.html`'s overlay is full-screen, `z-index: 9999`, and
is itself the clickable `<label>` that dismisses it (tapping *anywhere* on it, including over a
real button underneath, just dismisses the splash). It is shown once per browser session
(`sessionStorage`) and fades over ~2.2s. This review's own harness did not hit the problem itself —
its click helper verifies the coordinate lands on the real target via `elementFromPoint` and falls
back to a direct DOM `.click()` when something else (like this overlay) is in the way, so Start
fired correctly even in a brand-new profile. A mechanic's actual first physical tap on a freshly
opened session has no such fallback: if it lands anywhere on the splash before it finishes fading,
it dismisses the splash and does **not** reach the button underneath.
**Fix:** make the overlay `pointer-events: none` (or shorten/skip it) once its fade-out animation
starts, so a tap during the last stretch of the reveal reaches the real page.
**Accept when:** a tap anywhere on screen during the splash's fade-out activates the control
underneath it, not just the splash's own dismiss.

## Checkpoint 3 — `/v/{vin}/health`
**Passed, with one honesty finding (N3).** 12/12 measured checks on the real seeded 2026-10-13
corpus. Two screenshots (top verdict card, issues list), 390×844.

- **Seen (screenshot + DOM text):** header reads **"As of 2026-10-13T20:03:54 — serial
  COM3@115200"** — a raw, sourced timestamp + stream on every read, never a bare number. Verdict
  card: **"Active fault — Primary system: EVAP (evaporative emissions)"**, basis lines `stored:
  P0440` / `pending: P0440, P0455` / `permanent: P0440, P0456` / `2 Mode 06 test(s) failed this
  scan` / `every readiness monitor has completed since the last clear -- this is a live, measured
  fault, not a code waiting on a monitor` — all match the real seeded corpus exactly.
- **EVAP row (measured in page text):** the Mode 06 MID 3A reading renders **"404 vs limit 3965"**
  — the real large-leak self-test value against its real threshold, sourced straight from the
  night's Mode 06 read, not a placeholder.
- **Network row:** **"BCM: U1713-2F (network) ACTIVE this scan — check BCM supply and grounds
  first, then the bus (...). Do not clear codes before it."** — correct code, correct module,
  points at the documented upstream cause rather than the bus itself.
- **Issues order (measured, 6 items, in order):** (1) ESIM vacuum test (Test A) now, "Do not clear
  codes before it"; (2) the BCM/U1713-2F network issue, also "Do not clear…"; (3) a gap line for
  systems with no mapped module at all ("Not read this scan: Electrical supply, Air intake/boost,
  …"); (4) a gap line specifically for the grey-A6-gated systems ("not reachable — needs grey A6
  cable: Brakes/ABS, Steering, Restraints"); (5) a third gap line (see N3 below); (6) the
  evidence-to-attach reminder, correctly last. "Do not clear" appears exactly twice, on the two
  active-fault issues only — never pasted onto a gap or reminder line where it wouldn't belong.
  No placeholder `#`/empty-href links anywhere on the page.

### N3 (P1). One gap reason leaks a raw Python exception straight into the mechanic's issue list
**Seen (screenshot `shot_cp3_issues.png`, item 5; confirmed as real, not a test-harness artifact,
by grepping the source `C:\ProgramData\cuore\observations.jsonl` for the same string):**
> *"Not read this scan (not reachable — LinkUnavailable: could not open COM3@115200 (MES registry
> (Interface 0 Port), MES registry (Interface 0 Port Speed)): could not open port 'COM3':
> FileNotFoundError(2, 'The system cannot find the file specified.', None, 2).): Infotainment/
> cluster, Wheels/TPMS."*

This is the real `scan_coverage` observation's own `why` field for two systems the night's real
scan never reached, rendered verbatim. The very next line up in the same list (item 4) shows the
*correct* pattern for the exact same kind of gap — a plain-English reason, `"not reachable — needs
grey A6 cable"` — so the report clearly has a path for saying "why" in mechanic language; this one
case fell through to a raw adapter/driver exception string instead (`FileNotFoundError(2, '...',
None, 2)` repr and all).
**Fix:** when the recorded `why` for a gap is a raw exception/driver string rather than one of the
report's own known reason codes, either translate it to a plain sentence ("adapter not connected on
COM3") or fall back to the generic "Not read this scan" wording the no-mapped-module bucket (item 3)
already uses, rather than passing the exception through.
**Accept when:** no issue line on `/v/{vin}/health` ever contains a bare Python exception
repr/class name.

## Checkpoint 4 — `/v/{vin}/scans` list + diff
**Passed, with one confirmed defect (N4).** 7/7 measured checks. Real click on the actual Compare
button (a `method="get"` form, so a genuine navigation). Two screenshots (list, diff), 390×844.

- **Seen (list, real 2026-10-13 corpus, 3 sessions found by the 15-minute grouping window):** every
  row is labelled **`attempt — adapter not reachable`** or **`partial`** — none is a numbered
  "complete" scan tonight, so the plan chip correctly reads **"Scan 0 of 10"**. This is not a bug:
  `cuore/live/scanlog.py`'s own module docstring documents this exact rule as a deliberate
  2026-10-14 owner correction ("the chip was counting partial/debug reads and failed attempts as if
  they were real scans... overclaiming") — a scan only gets a number and counts toward the plan
  when CAN-C itself answered at least one module. Verified against the honest cause: tonight's real
  corpus never got past opening COM3 on any of its three sessions, so zero numbered scans is the
  correct, honest answer, not a missing feature.
- **Compare → diff page:** clicking the real Compare button navigated to
  `/v/{vin}/scans/diff?a=SCAN_2610131952&b=SCAN_2610132059`; the page rendered a real `Codes`
  diff section (`P0440 removed (stored)`, `P0440 removed (pending)`, `P0455 removed (pending)`, …) —
  genuine, not an error page.

### N4 (P1). The diff page's summary line prints the literal word "None" for an unnumbered scan
**Seen (screenshot `shot_cp4_diff.png`):**
> *"Scan None (2026-10-13T19:52:49, partial) vs Scan None (2026-10-13T20:59:22, partial)."*

**Source (confirmed, `cuore/web/templates/scan_diff.html` lines 18–19):**
```
Scan {{ a.number }} ({{ a.started }}{% if a.partial %}, partial{% endif %})
vs Scan {{ b.number }} ({{ b.started }}{% if b.partial %}, partial{% endif %}).
```
`a.number`/`b.number` is `None` for any non-"complete" scan (by design — see above), and Jinja
renders Python `None` as the literal text "None". The sibling page one click away,
`scanlog.html` line 31, guards the exact same field correctly: `{{ s.number or "" }}`. The diff
page's summary line is the one place in this checkpoint that doesn't carry that guard. A second,
related inconsistency in the same sentence: the list page distinguishes `attempt — adapter not
reachable` from `partial`, but the diff summary only tests the boolean `a.partial`, so an
`"attempt"`-status scan (`SCAN_2610132059`, shown as "attempt — adapter not reachable" on the list
page one click earlier) is relabelled plain `"partial"` here — the same scan, two different status
words, one page apart.
**Fix:** guard `a.number`/`b.number` the same way `scanlog.html` already does (`{{ a.number or ""
}}`), and reuse the list page's own three-way status wording (complete/partial/attempt) instead of
the single `partial` boolean, so the same scan reads the same way on both pages.
**Accept when:** the diff page never prints the string "None", and a scan's status word matches
between `/v/{vin}/scans` and `/v/{vin}/scans/diff` for the same scan.

## Checkpoint 5 — Job step 7 Mode 06 evidence picker
**Passed.** 11/12 measured checks (the one "failure" was this harness's own test asserting the
System dropdown's value equalled the literal string `"evap"`, when the real, correct value is the
human label `"EVAP (evaporative emissions)"` — confirmed correct both in the raw HTML and in the
rendered DOM; not an app defect). One screenshot, 390×844. Case opened via a direct POST to
`/v/{vin}/job/open` (same documented exception `MECHANIC_REVIEW_3` used — step 1/intake is out of
this checkpoint's scope); everything from there on was a real browser interaction.

- Navigated to `/v/{vin}/job?step=7&system=evap&codes=P0440` — this review's own first attempt at
  that navigation silently dropped `&system=evap&codes=P0440` (a bug in this harness's own
  `/json/new?<url>` helper, which truncates at the embedded URL's own `&`, confirmed by reading
  `location.href` back as just `...?step=7`) — fixed by navigating over the CDP websocket
  (`Page.navigate`) instead, confirmed afterward with the full query string intact. Noted here only
  because it's a trap worth remembering if anyone reuses this harness, not an app issue.
- With the query string landing correctly: the `+ Add a hypothesis` `<details>` auto-expanded and
  the System dropdown was correctly pre-selected to `EVAP (evaporative emissions)`, both matching
  `job.html`'s own documented no-JS prefill behaviour.
- Typed a real hypothesis into the actual `#hyp_text` field and submitted the real HTML form
  (`#manual-hyp-form`) with a genuine click — a new hypothesis card appeared.
- Opened that card's real "+ Evidence for" `<details>` picker (a click, not a direct DOM read) and
  confirmed the `<select>` offers **both** real Mode 06 fails from tonight's seeded corpus:
  `"Mode 06 EVAP 0.090" leak: FAIL 404 ms vs min 3965 ms (car, 2026-10-13)"` and `"Mode 06 EVAP
  0.020" leak: FAIL 6096 ms vs min 0 ms (car, 2026-10-13)"` — correct values, correct limits,
  correctly dated. Selected the first, clicked the real Save button, and confirmed after the save
  that the hypothesis card now shows that Mode 06 reading as **attached** evidence, not just
  offered in the dropdown.
- **Seen (screenshot):** the step header still shows **"Job is at step 2 →"** while viewing/editing
  step 7 — the same category of mismatch `MECHANIC_REVIEW_3_BENCH_JOB_2026-10-13.md` already
  reported as **R2** (traced there to `flow_bridge.py`'s `first_not_done` pinning low because
  `/job/open` never creates the open *visit* step 1 needs). Not re-diagnosed here — flagging only
  that it still reproduces under this checkpoint's otherwise-unrelated flow, so it isn't yet fixed.
  Also seen: a "Hypothesis added" toast briefly overlapped the right edge of the step-nav's primary
  button at the moment of the screenshot — cosmetic, self-dismissing, not followed up further.

## Checkpoint 6 — `/m/{vin}` Messages, EVAP chips, History
**Passed on content/honesty, with two confirmed defects (N5, N6).** 11/14 measured checks; the 3
"failures" were this harness's own overly strict assertions, explained below — not app bugs. Two
screenshots (Messages, History), 390×844 (dark owner-facing theme, correctly distinct from the
mechanic app's light theme).

- **Scan-done message (seen, screenshot + raw HTML), real text:**
  > *"Scan attempt 13 Oct 20:59 — the adapter could not be reached (no module answered). 0 of 10
  > complete scans on file so far. The engine computer's own test flags the network / can buses
  > system. The engine computer's own test says the fuel-vapour system is not holding vacuum
  > (large-leak test failed). Next: the mechanic runs the ESIM switch test. What you can do: keep
  > the fuel level between about 1/4 and 3/4 tank, click the fuel cap until it clicks, and don't
  > keep topping off after the pump stops on its own. Please don't clear the light."*

  Correctly honest per the documented 2026-10-14 "scan plan honesty" rule — never claims a
  completed scan for tonight's real "attempt" session; names both real system flags (network and
  EVAP) consistently with the Health report (checkpoint 3); gives a concrete next test and
  owner-actionable advice; closes with the standard safety line. (This review's own first assertion
  — requiring the literal word "EVAP" in addition to "fuel-vapour" — was simply too strict; the
  message is correct as written.)
- **EVAP chips:** both `PROMPT_RULES["evap"]` questions are present and real (`"Did you fill up in
  the last 2 days? ..."` with 4 answer chips; `"Is this car mostly short trips lately..."` with 2).
  Clicking the real **"Filled up, cap clicked, pump stopped normally"** chip closed that message and
  created a correctly-linked History entry: **"Fill-up / cap clicked: True / overfilled: False /
  from a reply to a CUORE message: Filled up, cap clicked, pump stopped normally."** — the
  chip→History pipeline works end to end for a real click, not just a direct POST.
- **History page:** Edit links present and correct (`/m/{vin}/edit/{id}`) for both entries on file.
  No Print label button anywhere — correct, since neither entry on file is a printable
  oil-change/fluid-service kind (`m_print.html`'s own stated scope).

### N5 (P1). The same owner question gets filed as a separate, un-deduplicated message per code
**Seen (measured, raw HTML of `/m/{vin}/messages`):** 45 total distinct messages on file for this
one VIN; of those, the electrical-system question **"Any battery work, jump start, or aftermarket
electrical fitted recently..."** appears **21 separate times**, word-for-word identical, and the
EVAP fill-up question appears **3** times — each a genuinely distinct message id (not a rendering
duplicate), confirmed by diffing the real HTML, not this harness's own doing.
**Root cause (`cuore/services/owner_events_bridge.py`, `_ensure_prompts_filed`):** the dedup key is
`(code, question_id)`, not `(family, question_id)` or `(vin, question_id)`. Every distinct DTC this
corpus ever recorded that maps into the same question family (`"electrical_supply"`/`"network"`
for the one real BCM module routinely reporting more than one U-/B-code across the evening's
several `module_dtcs` reads) independently re-files the identical shared question text — the dedup
only prevents the *same code* from asking the *same question* twice, not two different codes in the
same family from asking it.
**Fix:** key the dedup by `(family, question_id)` (or `(vin, question_id)`) instead of `(code,
question_id)`, so one owner question is asked once per concern, not once per code that happens to
touch it.
**Accept when:** no two messages in one vehicle's inbox carry the exact same question text at the
same time.

### N6 (P2). History has no reachable Delete or Undo — only Edit
**Seen (confirmed by reading source, not just a missed click):** `cuore/web/owner_routes.py`
registers working `POST /m/{vin}/history/{id}/delete` and `POST /m/{vin}/history/{id}/restore`
routes, but **no template** (`m_history.html`, `m_form.html`, the edit-confirm template) and **no
script** (`web/static/m.js`) references either path anywhere — grepped both. The History page
(screenshot `shot_cp6_history.png`) renders only an `EDIT` button per entry; there is no way for an
owner or mechanic to reach Delete (or therefore Undo) from the app itself.
**Fix:** either wire a Delete control (with the existing Undo affordance) into `m_history.html`/the
edit screen, or — if entries are meant to be permanent, attested reports — remove the dead
backend routes so they don't imply a capability the UI never offers.
**Accept when:** Delete is reachable from somewhere in the UI, with its matching Undo, or the
backend no longer carries routes nothing can call.

## Priorities
- **P0:** none found. Every checkpoint's core flow (wizard, freeze-frame capture, health verdict,
  scans/diff, evidence picker, messages/history) completed and produced correct, sourced output.
- **P1:**
  - N5 — duplicate owner-prompt messages (21 copies of one electrical question, 3 of the EVAP
    fill-up question), traced to `_ensure_prompts_filed`'s per-code (not per-family) dedup key.
  - N3 — a raw `FileNotFoundError`/`LinkUnavailable` Python exception string leaking verbatim into
    one gap line of the mechanic-facing `/v/{vin}/health` issues list.
  - N4 — the diff page (`/v/{vin}/scans/diff`) prints the literal word "None" for an unnumbered
    scan's number, and relabels an "attempt" scan as plain "partial" (disagreeing with the Scans
    list one click away).
- **P2:**
  - N1 — the wizard's cable "pictogram" is an unlabelled solid colour block, not a picture.
  - N2 — the opening splash can sit (briefly) on top of the very first real tap of a session.
  - N6 — History has a working Edit control but no reachable Delete/Undo, despite the backend
    routes existing.

## Regression tests to add
1. N5: assert that filing owner prompts for a VIN with many same-family codes on file (e.g. several
   distinct U-/B-codes all mapping to `"electrical_supply"`/`"network"`) produces at most one open
   message per `(family, question_id)`, not one per `(code, question_id)`.
2. N3: assert no issue line on `/v/{vin}/health` ever contains a Python exception class name or
   `repr()` (e.g. grep every issue string for `Error(` / `Traceback`), feeding it a gap row whose
   stored `why` is a raw adapter exception.
3. N4: assert `/v/{vin}/scans/diff` never renders the literal substring "None", and that a given
   scan's status word (`complete`/`partial`/`attempt`) matches between `/v/{vin}/scans` and
   `/v/{vin}/scans/diff` for the same scan id.
4. N1/N2: a DOM check that `.fscan-pictogram` either has a non-flat background (an actual image) or
   is removed, and that `.intro-overlay` sets `pointer-events: none` once its fade-out animation
   begins.
5. N6: either a check that `/m/{vin}/history/{id}/delete` is reachable from some real on-page
   control, or (if intentionally permanent) that the route itself is removed/403s.
6. Re-run this review's full scope (the harness -- `cp1_wizard.py` .. `cp6_messages.py` plus
   `common.py`/`server_app.py` -- is reusable as-is for a future pass) after N5/N3/N4 are fixed, to
   confirm the fixes hold under the same real browser walk.

## Data left on this VIN
None intended — every server in this review used a throwaway `CUORE_STATE_DIR` seeded from a
*copy* of the real observations file, never the live `:5000` instance or COM3.
