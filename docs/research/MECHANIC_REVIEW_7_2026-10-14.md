# CUORE — E2E re-test #7: Mods, MES handoff cards, Others' experience, Connect to car, Scans list/diff

**Tested:** `ZASFAKPN5J7B88115` (the Stelvio), against a throwaway `CUORE_STATE_DIR` per
checkpoint, each seeded *only* with the real `2026-10-13` lines copied verbatim out of
`C:\ProgramData\cuore\observations.jsonl` (read-only source, never written to), on this review's
own uvicorn server with `cuore.live.ops` monkeypatched with the fakes from
`cuore/tests/check_fullscan.py` (copied into this review's own `server_app.py`, same shapes: stored
P0440; BCM U1713-2F/B1176-97; a 46-PID ECM; two real Mode 06 MID fails, 404 ms vs 3965 and 6096 ms
vs 0, matching the night's real seeded corpus) so the guided scan / Connect-to-car / Mode 06
evidence picker all work with no real adapter. Never the live `:5000` instance, never COM3.
Headless Edge, one instance at a time (a fresh profile per checkpoint), cleaned up via
`cuore/tests/_edge_cleanup.py`'s own `kill_edge_profile` — 44 stray automation Edge processes left
over from an earlier session were found and killed before this review started. Driven over raw CDP
(websockets), same posture as `cuore/tests/check_bench.py` — real clicks on the actual on-screen
controls wherever the task called for a walk-through, not raw HTTP calls standing in for them,
each click verified to land on the real target via `elementFromPoint` before dispatching (see the
harness note under Checkpoint 1). Run as five independent, synchronous per-checkpoint scripts
(`cp1_mods.py` .. `cp5_scans.py`, sharing `common.py`/`server_app.py`, all in this session's
scratchpad — not committed to the repo), each with its own fresh server+browser+state dir, so a
cut-off leaves this file current through the last completed checkpoint and no single long-running
process to kill mid-flight. This file is written after each checkpoint completes, not held back
for the end.

Checkpoints: (1) `/v/{vin}/mods`, (2) MES handoff cards on Tests + Job step 6, (3) Others'
experience on a code page + Report, (4) the "Connect to car" button, (5) Scans list/diff after the
review-5 fixes. All five ran to completion; no checkpoint was skipped.

**Screenshot count: 8, exactly this review's own budget** (cp1: 2, cp2: 2, cp3: 2, cp4: 2, cp5: 0 —
every check in Checkpoint 5 is textual/DOM, so it borrowed nothing from a budget already spent by
Checkpoints 1–4).

## Checkpoint 1 — `/v/{vin}/mods`
**Passed.** 23/23 measured checks. Real click walk: catalogue card → detail page → fill and submit
the "Record that it was done" form with a real click on Record → redirected back with `?saved=1` →
confirmed the ledger entry, the Stock→Modified chip flip, and the non-stock chip on two other
pages. Two screenshots (`cp1_mod_detail.png` — Risks/Reversal/Verify/Sources on the detail page,
scrolled past the one-time intro splash; `cp1_mods_after_record.png` — the page right after the
real Record submission), 390×844.

**Harness note, not an app finding:** headless Edge's own HTML parser rendered a `U+FFFD`
replacement character in place of the rule line's em dash on direct navigation of this one page
(reproduced consistently across repeat navigations and a `Page.reload`), while a byte-level
re-fetch of the identical URL *inside the same browser session* (`fetch()` + manual UTF-8 byte
inspection at the exact offset) returned the correct `E2 80 94` bytes, and the server's own raw
HTTP response (checked independently with `urllib`, with and without `Accept-Encoding: gzip`)
was always correct UTF-8 at that position. Since the real bytes the server sends are verifiably
correct and a plain re-fetch in the same session decodes them correctly, this review treats it as
a headless-Edge HTML-parser artifact specific to this harness, not a defect — but cross-checked
every wording assertion below against the real HTTP response (not the live DOM) rather than
silently trusting the DOM text, and a human should still eyeball this page in a normal (non-headless)
browser once given how deterministic the artifact was.

- **Seen (real HTTP response, verbatim):** the rule line — *"Modifications — not diagnostics. CUORE
  diagnoses; it never performs coding or configuration writes itself — a modification is done in
  MES/wiTECH (or the car's own menu) via a handoff card below, and recorded here once it's done."*
  Present on the list page. The **detail page's own rule line is shorter** (ends at "...writes
  itself." and drops the "a modification is done in MES/wiTECH..." clause that explains *how* the
  rule is satisfied) — not a defect worth a numbered finding on its own (both wordings are honest
  and consistent with each other), but worth a mechanic knowing the two pages don't say quite the
  same thing.
- **Before any record:** "This car" showed the **Stock** chip and "No modifications recorded —
  stock configuration." — correct for a fresh ledger.
- **Catalogue card (compact, list page):** the paddle-shift entry renders with its confidence chip
  (`CORROBORATED`/`CONFIRMED`), a `Reversible`/`Not reversible` chip, and a risk-count chip — all
  three badges the task asked for are present without opening the detail page.
- **Detail page (full card), byte-156 warning visible (screenshot):** the heading itself names the
  byte (*"Paddle shift NA/Euro characteristic (CAN Setup byte 156)"*, module *"Body/BCM (CAN Setup,
  byte 156)"*), and the Risks list right below spells out the real risk substance: *"No documented
  UDS DID for this byte"*, *"pay close attention and only alter what you are attempting to alter as
  these settings can have dire consequences if changed unknowingly"* (sourced, attributed),
  *"Single-source procedure for the exact byte/bit values"*, *"BCM also carries alarm/immobiliser-
  adjacent configuration on this platform — 'it's just the body module' is not the same claim as
  'it's low-risk'"* — a mechanic reading top to bottom cannot miss that this is the byte-156 write
  and that it is single-sourced and not low-risk.
- **Handoff card ("Do it in MES"), real content:** *"Do this in MES: Body/BCM (CAN Setup, byte 156)
  → Body → CAN Setup → Adjustments tab → PROXI byte 156, bits 4-5"*, Menu path repeated, Before/
  After fields, and *"Source: https://giuliatech.com/t/multiecuscan-mes-popular-settings-
  compilation/80 (2026-10-14) (confidence: SINGLE-SOURCE)"* — sourced and confidence-labelled, not
  asserted as fact.
- **Recording a modification (real form, real click):** filled Name/From/To/Verification, clicked
  the actual Record button, redirected to `/v/{vin}/mods?saved=1`. The ledger card then showed
  *"Paddle shift NA/Euro characteristic (CAN Setup byte 156) — 2026-10-14T12:19:13 by mechanic
  (Tony) — NA (0x50) → Euro (0x40) — Tool: MES — Verification: paddles together now reach Neutral"*
  with a working Remove button, and the chip at the top flipped from Stock to **Modified**.
- **Non-stock chip cross-reference:** `/v/{vin}/health` and `/v/{vin}/systems/transmission_driveline`
  both render the chip *"Non-stock configuration: Paddle shift NA/Euro characteristic..."* once the
  modification is on file — the bridge's one `non_stock()` function genuinely reaches both pages,
  not just one.
- **Readability (measured, 390px, detail page):** every button/`a.btn` ≥44×44px (Connect to car
  119×48, Record 76×44, theme toggle 44×44, help FAB 52×52, feedback Send 62×44); no text under
  12px found among paragraphs/spans/list items/labels on the page.
- **Confirmed: MECHANIC_REVIEW_5's N2 (the one-per-session intro splash sitting on top of the very
  first tap) is not scoped to the freeze-frame panel alone.** This checkpoint's own click helper
  verifies the coordinate lands on the real target via `elementFromPoint` before dispatching (same
  posture review 5 used) — the very first attempt to click the detail page's own Record button
  landed on the splash's dismiss `<label>` instead, confirmed directly (`elementFromPoint` at the
  Record button's own coordinates returned the splash overlay, not the button). Not re-filed as a
  new finding (same root cause, same fix as N2) — recorded here only to widen that finding's known
  scope: it is not page-specific, and a mechanic's first real tap on *any* page's primary action can
  be swallowed by the splash, not only the freeze-frame panel's Start button review 5 found it on.

No other issues found in this checkpoint.

## Checkpoint 2 — MES handoff cards on `/v/{vin}/tests` and Job step 6
**Passed the core flow, with two confirmed defects (N1, N2).** 20/20 measured checks. Real
navigation, real waits for the client-side handoff JS to fetch and inject its card, real clicks on
the Tests page's own result buttons and the handoff card's own Import button, a real
`/v/{vin}/job/open` (the same documented exception reviews 3/5/6 used for step-1 intake) before a
real navigation to Job step 6. Two screenshots (`cp2_tests_handoff.png`, `cp2_job_step6.png`),
390×844.

- **Seen (real DOM, after the client-side fetch):** the `esim_commanded_vent_test` card renders
  correctly and is genuinely client-injected, not server-rendered (confirmed absent before the
  fetch resolves, present after) — *"Do this in MES: Engine/ECM (EVAP) → Engine → ECM → Actuators
  tab → ESIM / purge solenoid vent command"*, Menu path/Before/After fields, *"Run in MES: Engine →
  ECM → Actuators tab → ESIM / purge solenoid vent command; CUORE records the result."*, and
  *"Source: http://forum.multiecuscan.net/viewtopic.php?t=9514 ... (confidence: CORROBORATED)"*.
- **No developer notes visible (confirmed):** the card's text never contains `cuore_today`'s own
  internal note (*"MCP-only via obd2.run_actuator with the ACTUATE ECM consent phrase"*) — Review
  6's N finding on this ("The ESIM commanded vent test card exposes internal notes") is fixed; the
  template now deliberately keeps that string in a source comment only, confirmed by grepping the
  real rendered text for it.
- **Result recording works (real click):** clicking the row's own real "Inconclusive" button
  recorded the result; re-fetching the page afterward showed the row carrying the recorded result.
- **Job step 6, real open-work checklist (14 real steps from this VIN's real corpus, ids
  `evap-1`..`evap-6`, `network-1`..`network-3`, `adas-1`..`adas-2`, `body-1`..`body-3`,
  `body_comms-1`..`body_comms-3`, `chassis-1`..`chassis-2`): zero MES handoff cards render here.**
  Traced to source, not a flake: the handoff JS cross-references a checklist row either by
  `data-fact="checklist|test:<test_id>"` or by a loose substring match against the step's own text
  vs. an MES function's `name`. Job step 6's real open-work rows are keyed `checklist|<family>-<n>`
  (from the bulletin-driven open-work generator, `cuore/web/templates/_open_work.html`) — never the
  `test:<id>` form at all, so the id-based cross-reference can never fire there. The one
  `esim_commanded_vent_test` MES function does have a real test cross-ref, but no step's own text
  ("Run the purge/vent valve KOEO actuator test", evap-2) is a substring match either direction
  against its catalogue name ("ESIM commanded vent test"), so the fuzzy match also misses. The
  feature's own code comment (*"job.html's step 6 section sets `mes_handoff_vin = vin`"*) implies
  step 6 is a real placement for this feature; in practice, for this VIN's real checklist, it
  contributes nothing.

### N1 (P2). The handoff card's own "Import the MES log" form ignores its `hidden` attribute — it renders on every card, not just ones that expect a log
**Seen (screenshot `cp2_tests_handoff.png`, and confirmed with a direct computed-style check):** the
`esim_commanded_vent_test` card (an actuator test, correctly `log_expected: false` — there is
nothing to import for it) still shows a full "MES LOG/RECORDING FILENAME" input and an enabled
"Import the MES log" button. `form.hidden` is genuinely `true` in the DOM (the JS correctly never
un-hides it), but `getComputedStyle(form).display` reads `"flex"` and its bounding box is
431×106px — visibly rendered regardless.
**Root cause (`cuore/web/templates/_mes_handoff.html` line 23):** `.mes-handoff-import { ...
display: flex; ... }` is an unconditional author rule with the same specificity as (and declared
after) the browser's own default `[hidden] { display: none }` rule — the class selector wins, so
the `hidden` attribute is cosmetically inert for this one element on every card, log-expected or
not.
**Fix:** scope the rule so it only applies when the form isn't hidden, e.g.
`.mes-handoff-import:not([hidden]) { display: flex; ... }`.
**Accept when:** a card for a non-`log_expected` function (like `esim_commanded_vent_test`) shows
no Import control at all.

### N2 (P2, found while reproducing N1). Clicking that wrongly-visible Import button does a silent, broken page reload instead of nothing or an error
**Seen (confirmed with a real click, not inferred):** typed a filename into the real input and
clicked the real "Import the MES log" button. `location.href` changed from
`.../v/{vin}/tests` to `.../v/{vin}/tests?log_name=SCAN_2610080920.txt` — a native, un-wired HTML
form submission (the form has no `action`/`method` of its own, so it defaults to `GET` the current
page) — not the JS `fetch()`-based import handler, which only gets attached when
`fn.log_expected && vin` is true (correctly false here). No success or error message ever appears;
nothing gets imported (`GET /api/tests/{vin}/mes-scans` stayed empty after the click). The
underlying import route itself is fine — reached directly, it imports the same file correctly and
returns a real health line, confirming this is a UI-wiring defect, not a backend one.
**Fix:** once N1 is fixed (so this control only ever renders for a real `log_expected` function,
which always gets the `fetch()` listener attached), this symptom goes away on its own; as a
second line of defence, the template's `<form>` should not be left without its own inert
`action="javascript:void(0)"`/`onsubmit="return false"` fallback for a no-JS or listener-less state.
**Accept when:** clicking Import either runs the real fetch-based import (when wired) or does
nothing/shows a plain error (never a silent, un-wired page reload that discards what was typed).

No other issues found in this checkpoint. Readability measured clean: all result buttons on the
Tests page ≥44×48px (PASS/FAIL 178×48, Inconclusive/Not possible 178×44); smallest text on the
handoff card (the `dt` field labels) measured 13.6px, above the 12px floor.

## Checkpoint 3 — Others' experience on a code page (`P0456`, real curated data) and the Report
**Passed, with one honesty/UX finding (N3).** 29/29 measured checks, all against the **real**
`mes.experience` catalogue for `P0456` (no fixture — review 5's own log notes this code "landed
2026-10-07"), real curated rows included. Full real-click walk: expand the collapsed row list,
expand "+ Add what you found", fill and submit the real form, confirm the AJAX-inserted row, a
real Edit (native `window.prompt`, answered for real over CDP's `Page.handleJavaScriptDialog` —
never assumed or skipped), a real Delete, a real Undo, and a real Flag on a curated row (another
native prompt, answered the same way). Two screenshots (`cp3_code_page_added.png`,
`cp3_mobile_add.png`), 390×844.

**Harness fix made along the way, not an app issue:** the row list (`<details class="card-details">`)
is collapsed by default — this headless Edge build lays out a *closed* `<details>`'s content with
`content-visibility: hidden` rather than the older `display: none`, so `getBoundingClientRect()`
still reports real (but un-hit-testable) geometry for a hidden row's Edit/Delete button. A coordinate
click at that geometry lands on whatever real content happens to be underneath, not the button —
this harness's click helper was extended with a guaranteed final direct-DOM `.click()` fallback (it
already existed on the plain `click()` helper, added to the new dialog-aware one too) and the test
itself was corrected to really click the row list's own summary open first, same as a mechanic
would have to.

- **Seen (real DOM):** the card's summary read **"Others' experience (10) — 10 curated"** before
  adding anything — the counts header is real and matches the real curated catalogue size for this
  code.
- **Add as Mechanic with a name (real form, real click):** left the role on its default (confirmed
  the hidden `role` field is already `"mechanic"` without clicking the chip — matches the chip's
  own `aria-pressed="true"` default), typed a name and note, clicked the real Save button. The new
  row appeared in the list via AJAX (no page reload) with the **Mechanic** chip and the typed name,
  both genuinely inserted into the DOM, confirmed via `data-exp-id`.
- **Edit (real native dialog):** clicked the row's own Edit button; a real `window.prompt` opened
  (confirmed by its CDP `type: "prompt"` event, not inferred), answered with new text over
  `Page.handleJavaScriptDialog`; the row's note text changed in the DOM to the exact text supplied
  to the dialog.
- **Delete + Undo (real clicks):** Delete hid the row and inserted a real **"Deleted. Undo?"** link;
  clicking that real link un-hid the row again — both state changes measured in the DOM, not
  assumed from a 200 response.
- **Rate:** rating is set at add-time (the form's own Rating select, `helped`/`unsure`/`wrong`) —
  there is no separate post-hoc "rate" control on a row; this matches the template, not a gap.
- **Flag a curated row (real native dialog):** confirmed the curated row offers **"Flag as
  wrong/outdated"** and genuinely has no Edit/Delete controls at all (never just visually disabled).
  Clicking Flag opened a second real `window.prompt`, answered over CDP; the button then read
  **"Flagged — thanks"** and became disabled — a real, confirmed round trip.
- **Counts header does not live-update after an AJAX add:** before/after the real Save click, the
  summary's `(N)` count stayed at the server-rendered 10 — not asserted as a defect (the row itself
  renders immediately and correctly; only the parenthetical tally is stale until the next full page
  load), but worth a mechanic knowing the number next to "Others' experience" can undercount by one
  right after they add something, until they reload.
- **Mobile `/m/{vin}` "+ Add what you found" (real click):** present, wired to `experience.js`
  (confirmed `data-exp-add-form`/`data-exp-card` and the script tag), a real click expands it, and
  the Mechanic radio is checked by default — consistent with the desktop chip's default.
- **Report page:** the mechanic-added link (added earlier in this same checkpoint) renders
  read-only with its **Mechanic** chip and the typed name, as its own existing regression suite
  checks — confirmed again here against a real, not fixtured, add.

### N3 (P2). The real "+ Add" form never opts out of live-verifying the URL, and nothing on screen says so while it waits
**Seen (confirmed with a real click, real timing):** `cuore/web/static/experience.js`'s
`wireAddForm` POSTs `{scope, url, title, kind, role, name, note, rating, confirm_duplicate}` to
`/api/experience/{vin}/inputs` — it never sends a `verify` field. The API's own model
(`cuore/api/experience.py`) defaults `verify: bool = True`, so every real on-page submission
triggers a real outbound network check of the submitted URL (`cuore/live/experience_inputs.py`'s
`verify_entry`/`_http_get_ok`, up to a 10-second timeout) before the server replies. This review's
own first attempt checked the result after 1.2s (a reasonable guess for a "save a note" action) and
found nothing had happened yet; only waiting the full ~10+ seconds let it complete. The status line
shows **"Saving…"** the instant the button is clicked and never changes wording while this real
network round trip runs — a mechanic on a slow or dead shop connection has no way to tell the save
is still legitimately in progress rather than stuck. Separately worth noting: `check_experience_page.py`'s
own regression suite always passes `"verify": false` on every add it tests, so this real-world
latency is never exercised by the existing automated checks at all.
**Fix:** either have the add form explicitly pass `verify: false` for a fast, synchronous save
(verifying asynchronously afterward, same as how a duplicate-URL check already round-trips), or
change the status text while waiting (e.g. "Checking the link…") so a multi-second wait doesn't
read as a hang.
**Accept when:** a real click on Save either completes in about a second, or the on-screen status
text changes to make a multi-second wait legible as "checking the link", not silence.

No other issues found in this checkpoint.

## Checkpoint 4 — the "Connect to car" button
**Passed.** 21/21 measured checks, two real servers (the happy-path fakes, and a second server
whose `ops.probe` was made to raise the live layer's own real `LinkUnavailable` text copied
verbatim from the real seeded corpus — never invented refusal copy), real clicks throughout,
including a genuine `Emulation.setScriptExecutionDisabled` pass to prove the no-JS fallback with
script execution actually off, not just "didn't click the enhanced path". Two screenshots
(`cp4_drawer_pause.png`, `cp4_drawer_refusal.png`), 390×844.

- **Fallback link without JS (real, script execution off):** `#connect-car-btn` is a plain `<a
  href="/v/{vin}/scan" data-vin="...">Connect to car</a>` — confirmed present in the DOM with script
  execution genuinely disabled over CDP (`Emulation.setScriptExecutionDisabled: true`), and a real
  click on it navigated straight to the guided-scan wizard's `idle` phase — the exact page
  `cuore/web/fullscan_routes.py` already serves with zero JS, reached by the button's own href, not
  a dead end.
- **Inline drawer, happy path (real clicks, screenshot `cp4_drawer_pause.png`):** with JS on, a real
  click opened the drawer showing the honest pre-check list in order — **"✓ Adapter found", "✓ Bus
  verified", "✓ VIN matches", "✓ Guided scan started"** — then paused with **"Fit the blue A5 cable
  (can_ihs), then Continue"**. A real click on the drawer's own **Continue** button advanced to
  **"Fit the grey A6 cable (can_ch), then Continue"**; a real click on **Skip** advanced to
  **"Remove the cable, then Continue"**; a real click on the final **Continue** produced **"Scan
  saved."** with real, working **Open scan** / **Health report** links, immediately before the
  drawer's own 900ms auto-reload (`connect.js`'s own `renderSummary`) fired — caught deliberately
  inside that window, not after.
- **Refusal wording (real, screenshot `cp4_drawer_refusal.png`):** a real click against the
  refusal server showed the live layer's own real text verbatim — *"could not open port 'COM3':
  FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"* — the exact wording
  this review's own Checkpoint-3-adjacent real corpus already carries (same string
  MECHANIC_REVIEW_5's N3 found leaking into a health-report issue line), confirmed here rendering
  correctly in its *intended* place — plus a real, working **Try again** button.
- **Seen (screenshot `cp4_drawer_refusal.png`), minor/cosmetic:** the refusal's own real wording
  appears twice in a row — once as the failed checklist step's own line (**"⚠ Find the adapter:
  could not open port 'COM3': ..."**) and again immediately below as the standalone error paragraph
  (`connect.js`'s `renderChecks` and `renderRefusal` both append it). Not confusing or dishonest —
  the exact same real wording both times — just a literal repeat a mechanic reads twice in two
  lines.
- **Readability (measured, 390px):** Connect to car 119×48px, drawer Continue 86×44px, Skip
  56×44px — all ≥44×44; every measured text node in the drawer (checklist items, the pause
  heading) is 14px, above the 12px floor.

No other issues found in this checkpoint.

## Checkpoint 5 — `/v/{vin}/scans` list + diff after the review-5 fixes
**Passed the core fix, with one confirmed regression-of-scope (N4).** 12/12 measured checks. Real
click walk: real navigation to the list, a real selection on the Compare form's own second
`<select>`, a real click on the real Compare button, landing on the real diff page. No screenshot
needed for this checkpoint — every check here is textual/DOM, and this review's own 8-screenshot
budget was already used by Checkpoints 1–4.

- **Confirmed: review 5's N4 fix holds where it was applied.** The list table's own `<td>`
  (`scanlog.html` line 31, `{{ s.number or "" }}`) never prints "None" for any of this VIN's three
  real unnumbered scans — each renders its chip correctly instead: **"attempt — adapter not
  reachable"** for `SCAN_2610131952`, **"partial"** for the other two. The diff page a real Compare
  click actually reaches also never prints "None" (its own `{{ a.number or "" }}`/`{{ b.number or
  "" }}` guard, and the three-way status wording, both hold), and its status word for each scan now
  agrees with the list page's own wording for the same scan — the second half of review 5's N4
  (the diff page relabelling an "attempt" scan as plain "partial") is also fixed.
- **Plan chip:** **"Scan 0 of 10"** — correct and honest (zero numbered/complete scans in tonight's
  real corpus), matching review 5's own CP4 finding on this identical real data; not re-verified as
  a new finding, just confirmed still true.

### N4 (P2). The Compare dropdown (list page) still prints the literal word "Scan None" — the same bug class as review 5's N4, in a second spot its fix didn't reach
**Seen (confirmed with the real page, real `<select>` contents):** both of `scanlog.html`'s Compare
`<select>` pickers render every one of this VIN's three real scans as literally
**"Scan None — 2026-10-13T19:52:49"** (and the other two timestamps) — all six `<option>` elements
across both dropdowns, confirmed by reading their own `textContent` in the live DOM, not inferred
from source alone.
**Root cause (`cuore/web/templates/scanlog.html` lines 62 and 68):**
```
<option value="{{ s.id }}" ...>Scan {{ s.number }} &mdash; {{ s.started }}</option>
```
Two lines above, the table's own `<td>` for the very same `s` already guards this exact field
(`{{ s.number or "" }}`, line 31) — the Compare dropdown just below it, built from the same loop
variable in the same template, was never given the same guard.
**Fix:** `{{ s.number or "" }}` in both `<option>` lines, same as the table cell three lines above
them.
**Accept when:** neither Compare `<select>` ever renders the literal substring "None" for any
unnumbered scan.

No other issues found in this checkpoint.

## Priorities
- **P0:** none found. Every checkpoint's core flow (modifications record/non-stock chip, MES
  handoff cards, Others' experience add/edit/delete/flag, Connect to car, scans list/diff) completed
  and produced correct, sourced, honest output.
- **P1:** none found.
- **P2:**
  - N1 — `cuore/web/templates/_mes_handoff.html`'s `.mes-handoff-import` CSS rule
    (`display: flex`) defeats its own `hidden` attribute, so the "Import the MES log" form renders
    on every handoff card, not only ones that actually expect a log (confirmed on
    `esim_commanded_vent_test`, which has nothing to import).
  - N2 — found while reproducing N1: clicking that wrongly-visible Import button does a silent,
    un-wired native page reload (the filename leaks into the URL's query string) instead of running
    the real import or showing any error, because the JS only attaches its real handler when
    `log_expected` is true.
  - N3 — the real "+ Add what you found" form never sets `verify: false`, so every real submission
    waits on a real outbound network check (up to 10s) with the status frozen at "Saving…" the whole
    time — and the existing regression suite always passes `verify: false`, so this real latency is
    never exercised by it.
  - N4 — the Compare dropdown on `/v/{vin}/scans` still prints the literal word "Scan None" for an
    unnumbered scan — the same bug class review 5's N4 fixed on the table cell and the diff page's
    summary line three lines above it, left unguarded in this one spot.
- **Also confirmed, not re-filed:** MECHANIC_REVIEW_5's N2 (the one-per-session intro splash sitting
  on top of the very first tap) reproduces on the Modifications detail page's own Record button too
  (Checkpoint 1) — widens that finding's scope rather than adding a new one.

## Regression tests to add
1. N1/N2: a DOM check that `.mes-handoff-import` is not visibly rendered (`getBoundingClientRect()`
   is zero, or `getComputedStyle().display === "none"`) whenever its `hidden` attribute is true, for
   every function the catalogue has — not just the one card a hand-written test happens to check.
2. N3: a check that drives `POST /api/experience/{vin}/inputs` the way the real page does (no
   `verify` field at all, not `verify: false`) against a URL this review's own harness controls (so
   the timing is deterministic), and asserts the save still completes and the status text changes
   at some point rather than staying frozen at "Saving…" indefinitely.
3. N4: assert neither `<select name="a">` nor `<select name="b">` on `/v/{vin}/scans` ever renders
   the literal substring "Scan None" for an unnumbered scan — same fixture shape
   `check_scanlog.py`/review 5's own diff-page check already uses, just pointed at the dropdown
   instead of the summary line.
4. Re-run this review's full scope (the harness — `cp1_mods.py` .. `cp5_scans.py` plus
   `common.py`/`server_app.py`/`server_app_refusal.py` — is reusable as-is for a future pass) after
   N1–N4 are fixed, to confirm the fixes hold under the same real browser walk.

## Data left on this VIN
None intended — every server in this review used a throwaway `CUORE_STATE_DIR` seeded from a copy
of the real observations file (filtered to the 2026-10-13 lines only), never the live `:5000`
instance or COM3. The one real mutation made against the *real* `mes.experience` curation store
during Checkpoint 3 (a flag filed against a real curated row for `P0456`, `flag_kind: "outdated"`,
note *"canister P/N changed since"*) was made against this review's own throwaway `CUORE_STATE_DIR`
as well — `mes.experience`'s curated catalogue itself (the read-only source table) was never
written to; only `cuore.live.experience_inputs`' flag ledger, under the throwaway state dir, picked
up the entry.
