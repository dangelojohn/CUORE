# Bench screen UX review (`/v/{vin}`)

**Date:** 2026-10-26. **Scope:** read-only review of `cuore/web/templates/bench.html`, `cuore/web/bench_routes.py`,
`cuore/services/bench_bridge.py`, `_vbar.html`, `_next_session_rows.html`. Rendered the Stelvio
(ZASFAKPN5J7B88115) from a copy of the state dir (never COM3, never ProgramData), headless Edge at 400x800 and
768x1024, light and dark. Screenshots and raw numbers: `scratchpad\bench_review\` (`bench_{400,768}_{light,dark}_{first,full}.png`,
`measure.json`). Heights below are px as rendered today. Car state: not connected, fuel 93.7 % (above window).

## 1. What the screen is for today (reading order)

| # | Element | Purpose | h @400 | h @768 |
|---|---|---|---|---|
| 0 | Header + hero + tab strip (`_vbar`) | identity, verdict chip, Connect to car, scanner chip, tabs | 412 | 353 |
| 1 | The call (`#bench-call`) + "Why?" fold | one line: "Fuel 93.7 % - burn below 85 %, then run a drive cycle" | 113 | 89 |
| 2 | Go-to chips (9 + Scan fold) | pages; at 400 one sideways-scrolling row (~1590 px wide, 4 chips visible) | 44 | 88 (2 rows) |
| 3 | Work on now (row, taps to Job) | "P0440 . P0456 - Permanent . last seen 14 h ago" | 44 | 44 |
| 4 | Next connection fold | "8 steps (0 done)"; opens by itself only when live | 46 | 46 |
| 5 | Last scan fold | "14 h ago, partial, 2 active codes"; inside it: Standing list with the **Fixed** buttons, History, coverage | 46 | 46 |
| 6 | Inspection cards (3 of the 19 steps) | per step: text, READY/BLOCKED/DONE chip, bulletin, parts, tools fold, "Mark done" tick, folded procedure + OK/Fault found/Skipped + note + Save | 570 (162/227/162) | 399 (131/116/131) |
| 7 | Resume line | "2 of 19 done" | 72 | 72 |
| 8 | Fuel gate / Readiness / Mode 06 boxes | fuel level (repeats the call), monitors | 201 | 96 |
| 9 | Parts for this job + Tools fold | job-level shared parts | 154 | 110 |
| 10 | Code chips (B1040, B1176) + legend | shortcuts to code pages | 69 | 69 |
| 11 | Vehicle facts card | tyre pressures, recall line | 266 | 216 |

Total scroll height: 2420 at 400, 1978 at 768. Not rendered here but conditional: complaint quote, MIL box, case hint.

## 2. Measurements

**First screen, 400x800** (intro overlay dismissed): hero stack eats 412 px (51 % of the viewport). Visible below it:
the call, the first 4 Go-to chips (rest hidden behind a fade), Work on now, Next connection, Last scan, and 21 px of
the first inspection card, which is a DONE step. No Fixed button, no READY step, no connection state other than the
hero chip. `check_bench.py` passes (card top 779 < 800) but the card is not usable there.
Also seen: the header's LIVE LINK / STELVIO FACTS / PARTS icons overlap the CUORE wordmark at 400.

**First screen, 768x1024:** hero 353 px. Visible: call, two rows of Go-to chips, Work on now, the two folds, DONE card
(evap-1), BLOCKED card (evap-2, "MES not running - to unblock: Open Live"), top of the READY card (evap-3, starts 1008).
The first actionable step is on screen only as a sliver. No Fixed button (inside the closed Last scan fold).

**Taps from landing (car not connected):**

| Goal | Taps | Notes |
|---|---|---|
| Top issue (code page) | 2 | open Last scan, tap the 12 px code chip; or 1 tap to Job via Work on now |
| Its Fixed | 2 + scroll | open Last scan, then Fixed (y 884 at 400: below the fold). Two codes, two Fixed buttons, no "all" |
| Next inspection step, recorded | 4-5 | scroll ~1 screen, open the card, pick outcome, Save. The visible "Mark done" tick does nothing alone: it is bound (`form=`) to the folded form and no JS submits it (read from markup; confirm on the tablet) |
| Connect to car | 1 | hero button, 14 px text |
| Electrical path of the top fault | 3 | Last scan, code chip, scroll to "Electrical path for P0440" on the code page. The Go-to "Electrical layout" chip is the generic page, not the fault's path |
| Job page | 1 | Work on now row, Go-to chip or tab: three ways |

**Under 16 px (visible text):** 12 px: header icon labels, tab "More…", VIN tail, odometer, scanner chip, "Live 0/3",
verdict chip, Scan 4 of 10, partial, Permanent, code chips, S2125000002 bulletin chip, precondition and tool chips,
legend chips, "Open Live" link. 14 px: vehicle name, Connect to car, Save, procedure and "Tool:" paragraphs, inspect-step
list, Done-summary, hero "Full VIN" block. The template sets `.bench .small` to 1rem but these elements bypass it.
**Under 44 px:** "Mark done" tick 28x28 (its label is 44 tall); "Open Live" 14 px high; ~13 inline links 14-23 px high in the
card area; code chips 55x44 are fine in size but 12 px in text; scan id link 23 px high. Go-to chips, Work on now, folds,
Fixed (88x44), Save (59x48) meet 44.

**Dark theme (tokens read from the page):** ink on surface 16.5:1, ink-2 on raised 8.9:1, chronic amber on its tint 6.8:1,
ok green on its tint 6.1:1, returned red on its tint **4.6:1** (passes AA only at normal size; the 12 px chips are the risk).
The call's amber box reads well. Red Connect to car button stays distinct in both themes.

## 3. Judgement against the intent

1. **"What do I do now, on this car, right here?"** The call answers it, but with the *fuel gate*, one condition, not
   with the job ("2 active faults, P0440 and P0456; EVAP test blocked until fuel < 85 %"). It is a good line, wrong
   scope for a mechanic who is under the car: it says nothing about the 19 steps or what to touch next.
2. **Primary task.** Layout says "fault board" (call, Work on now, Standing, Next connection come first); the page
   title, progress and 570 px of cards say "inspection flow". The inspection steps start at y=779 (400) behind four
   headers, and the first card is a finished step. Done steps should not lead.
3. **Duplication.** Four things say "what next": the call (fuel), Work on now (codes), Next connection (8 connect-time
   steps), and the cards (19 inspect steps) plus Resume. Codes appear in Work on now, Standing, History, code chips and the
   hero chip. Fuel appears in the call and again in the Fuel gate box (93.7 vs 93.725). Next connection and the cards both
   carry "do X next" with different Done controls (Done/Undo vs Mark done + Save).
4. **Wrong-signal bits.** The Go-to "System: Network / CAN buses" chip is derived from `bench.shortcuts[0]`, the body code
   B1040, while Work on now is about P0440/P0456: the chip points at the wrong fault's system. The scanner chip is
   green when "not running" and red when connected (`_vbar.html`): inverted for a bay glance.
5. **State words.** Bench uses Permanent / Active / Cleared, unverified (chips), READY / BLOCKED / DONE (steps), Done / Undo
   (Next connection), OK / Fault found / Skipped (outcome), and the hero's "Unverified repair". Codes page and Job use
   Returned after a clear / Chronic / Seen once and Verifying / Proven fixed (`codes_call.py`). "Fixed" button correctly
   maps to Verifying, but the bench never shows the Verifying / Proven fixed words, so the loop (diagnose, prove, learn)
   is invisible here. READY vs the Job page's wording was not compared page-by-page.
6. **Junior vs senior.** Junior needs: the next step, in plain words, with "open in layout" one tap away. Senior needs:
   the electrical path and pass criteria for the top fault, and the verdict basis. Today both are 2-3 taps and a scroll away;
   "Why?" is the only fold that earns its place.

## 4. Recommended UX

### Proposed first screen, 400x800 (compact hero ~150 px)
```
[CUORE]            [?] [sun] [menu]        <- header, no overlapping labels
Stelvio 2018 . ...J7B88115  [Connect]      <- one row: name, state chip, Connect
Not connected . 12.4 V last . scan 14 h
-------------------------------------------
 NOW: Fuel 93.7 % - burn to < 85 %, then
 run a drive cycle        (P0440 P0456)  [Why?]
-------------------------------------------
 NEXT STEP (3 of 19)                READY
 Check hose routing                       <- first not-done step, not a DONE one
 [ OK ] [ Fault found ] [ Skip ]  [open >] <- 44 px, one tap = saved, Undo toast
-------------------------------------------
 Faults (2)   P0440 Permanent 14 h  [Fixed]
              P0456 Permanent 14 h  [Fixed]
 Go to: Job  Tests  Live  Path P0440 ->
```
### Proposed first screen, 768x1024 (same order, two columns below the call)
```
[Stelvio ... Connect]  Not connected | 12.4 V | scan 14 h | 2 of 19 done
+------------------------------------------------------------+
| NOW: Fuel 93.7 % - burn below 85 %, then drive cycle  Why? |
+---------------------------+--------------------------------+
| NEXT STEP 3/19   READY    | FAULTS            Fixed        |
| Check hose routing        | P0440 Permanent 14 h  [Fixed]  |
| Pass = ... (one line)     | P0456 Permanent 14 h  [Fixed]  |
| [OK][Fault found][Skip]   | Electrical path for P0440  ->  |
| then: step 4 (BLOCKED:    | Go to: Job Tests Live Scan     |
| MES not running)          |                                |
+---------------------------+--------------------------------+
 > All 19 steps (2 done)  > Next connection (8)  > Last scan  > Facts
```
### Order of sections
Hero (compact) > Call > Next step card (with the one-tap outcome) > Faults with Fixed > Go-to (6 chips) > "All 19 steps"
fold (grouped Done / Ready / Blocked) > Next connection fold > Last scan / readiness / Mode 06 / parts / facts folds.

### Two states
- **Not connected (today):** call leads with the blocker (fuel, MES not running) and the physical step that needs no car;
  Connect to car is the one red button; Next connection stays folded; blocked steps show their unblock in the row.
- **Connected:** hero chip turns to a live strip (link state, battery V, ignition, last read age); call changes to the
  live next move ("Run purge/vent KOEO test: 12.6 V ok, engine off"); Next connection opens as the primary list; the fuel
  box becomes a live reading; Fixed offers "Verify now" (verify_repair) and the card shows Verifying with the reading
  that will prove it.
- **Procedure running:** replace the call with the procedure name, step n of N, the one instruction, a Stop/Abort button
  and live values; collapse everything else; keep voltage and link state pinned (never scroll away).

### Recommendations (ordered by mechanic benefit)

| # | Change | Touches | Effort |
|---|---|---|---|
| 1 | Lead with the **next undone step** (skip DONE, show "3 of 19"), with OK / Fault found / Skip as three 44 px buttons that save in one tap (POST, Undo toast); drop Save and the dead "Mark done" tick | `bench_bridge._next_actions` ordering; `bench.html` `.bench-card`, `.bench-outcome-fields`, `.bench-check`; `bench_routes.bench_mark_done` (JSON or redirect+toast) | M |
| 2 | Compact bench hero: one row, drop image band, fix header overlap at 400; target call top < 200 px | `_vbar.html` (bench branch), `cuore.css` "Bench compact hero" | M |
| 3 | Put **Faults + Fixed** on the first screen; retire the closed "Work on now" row plus Standing-in-Last-scan duplication into one "Faults" list (priority ladder, last seen, Fixed). Fixed row names its code | `bench.html` `#bench-worknow-row`, `.bench-lastscan-codes`; `codes_call.standing_views` | M |
| 4 | Make the call speak for the **job** (faults + gate + connection), keep fuel readout as the clause that blocks; drop the separate Fuel gate box or fold it | `bench_bridge.call_line`; `bench.html` `.bench-gates` | S |
| 5 | Two-state header: scanner chip colour fixed (connected = green/live, not running = neutral); live strip with volts; Next connection `open` when live (already) and promoted above the cards when live | `_vbar.html` line ~157; `bench.html` `#bench-next-session`; `bench_bridge._next_session` | M |
| 6 | One-tap "Path for P0440" chip in the Faults list and fix the System chip to follow the fault named in the call, not `shortcuts[0]` | `bench.html` Go-to block (`_top_code`); `bench_bridge._shortcuts` | S |
| 7 | Text and target sweep: 16 px minimum for chips, bulletin, tool, legend, Save, procedure lines; 44 px for Open Live and inline links; dark-mode returned-red chip text to a lighter token (>= 7:1) | `bench.html` style block (`.chip` override scoped to `.bench`), `cuore.css` tokens | S |
| 8 | Shared state words: show Verifying / Proven fixed on fault rows exactly as Job and Codes do; map READY/BLOCKED/DONE to the list-organisation ladder; one vocabulary note in the template | `codes_call.BOARD_CHIPS`, `bench.html` state badges | S |
| 9 | Group the 19 steps in one "All steps" fold: Ready, Blocked, Done (done last, dimmed); Go-to to 6 chips + "More" (Sensor health, Fuses, Dossier, Scan) | `bench.html` `.bench-actions`, `.bench-go` | M |
| 10 | Procedure-running mode (call replaced by step n of N, pinned voltage/link, Abort) | new partial under `bench.html`, `cuore/live` status feed | L |

### What should NOT change
- The one-line call with the "Why?" fold and the verdict text/basis; the fuel-gate wording (no invented litres: keep "n/a - tank
  capacity not sourced").
- Fixed meaning "records the repair and starts verification"; Proven fixed only from readings (core directive).
- Per-step procedure, pass criteria, if-abnormal, doc link, bulletin chip, parts and tools: the evidence trail stays one tap deep.
- Outcome vocabulary OK / Fault found / Skipped, and Fault found filing a mechanic note.
- "Open in layout" and "Electrical path for:" (kept, and made more reachable, never removed).
- Connect to car as a single deliberate tap (`connect.js`: never connects on page load); no raw adapter contact from the page.
- Light/dark tokens, 820 px column, 44 px folds, Go-to chips as a row (wrapping on tablet).
