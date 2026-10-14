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
review-5 fixes.

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
