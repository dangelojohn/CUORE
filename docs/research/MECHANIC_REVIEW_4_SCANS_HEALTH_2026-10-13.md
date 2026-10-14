# CUORE — E2E re-test #4: Scans, Health, Scan wizard, Live board, Bench/Job cross-check

**Tested:** `ZASFAKPN5J7B88115` (the Stelvio), against a throwaway `CUORE_STATE_DIR` seeded
*only* with the 35 real lines dated `2026-10-13` copied verbatim out of
`C:\ProgramData\cuore\observations.jsonl` (tonight's real bench reads: three natural scan
sessions at ~19:52, ~20:24 and ~20:59), on a server this review started itself (own
`cuore.live.ops` fakes, same posture as `cuore/tests/check_fullscan.py`, so hardware-gated
surfaces could be driven without a real adapter) — never the live `:5000` instance, never COM3.
Headless Edge, one instance, one profile, cleaned up via `cuore/tests/_edge_cleanup.py`.

**Run interrupted — most of the planned scope was not reached.** The orchestrating script was
killed mid-run (twice) by an out-of-band stop before it could walk past the Bench and Scans-list
pages. Per instruction, this report covers only what was actually observed live, in the browser,
before that happened, and marks everything else **not reached in this run** rather than guessing
or re-running. One screenshot survived (`01_bench_768.png`, 768×1024); a second
(`02_scans_list_768.png`) was captured in an earlier pass of the same script but the file was
deleted before this report was written, leaving only its structured measurements (JSON) on record.

## What was actually reached

- **`/v/{vin}` (Bench).** Loaded clean, 200, title
  `"Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir — Bench · 0/24 · ACTIVE_FAULTS"`. Verdict chip reads
  **"Active faults"**, correctly sourced from tonight's live DTCs in the seeded corpus (dossier
  verdict logic reads `_latest_live_dtcs`, which is exactly `observations.jsonl`) — this is the
  "Bench verdict now reading ACTIVE FAULT from the live data" item in scope, and it checks out.
  Vehicle name never fell back to "(unnamed vehicle)". The resume card correctly names
  **`SCAN_2610132059`** (tonight's newest real scan, `2026-10-13T20:59:22`, `serial COM3@115200`)
  with working-looking `Open scan` / `Health report` / `Compare with previous` buttons, and a
  `Scan 3 of 10` chip.
- **`/v/{vin}/scans` (Scans list).** 3 real scans listed, newest first:
  `SCAN_2610132059`, `SCAN_2610132024`, `SCAN_2610131952` — matching the three natural ≥15-minute
  gaps in tonight's seeded data. `Scan 3 of 10` plan chip and the `Compare` form (two `<select>`s
  posting to `/v/{vin}/scans/diff`) were both present in the DOM.

## Findings

### N1 (P2). Bench's resume card shows two contradictory "how old is this" signals on the same screen
**Seen (screenshot, `01_bench_768.png`):** directly under the task list, the resume card reads
**"last scan 6 d ago · stale (> 24 h) · 0 of 24 done"** — but the card immediately above it on the
same page names **`SCAN_2610132059`, `2026-10-13T20:59:22`** as the open scan, which (current time
tonight ~21:3x) is well under an hour old. A mechanic reading top-to-bottom sees "today, 20:59"
immediately followed by "6 days ago, stale" with nothing distinguishing which clock each is on.
This may be two genuinely different notions (a live-OBD scan session vs. a separate MES-log-based
"last visit" figure) rather than one wrong number, but the page does not say so, and nothing here
confirms it is fine — only that it reads as a direct contradiction to someone not already familiar
with the two data sources.
**Fix:** label the two dates by what they each measure ("last live read" vs. "last shop visit" or
similar), or reconcile them so the same screen doesn't show "now" and "6 days ago" as if answering
the same question.
**Accept when:** the resume card never shows two unexplained ages for "how recent is this" in the
same glance.

### N2 (P1, unconfirmed root cause — flag for a focused re-check). Dead-link sweep on the Scans page: 39 of 40 links failed
**Seen (measured, `urllib` direct from the review's own process, 8s timeout per link, not through
page JS):** of 40 unique `<a href>` targets on `/v/{vin}/scans`, only `/live` returned a response
at all (a 500), and the remaining 39 — including `/v/{vin}`, `/v/{vin}/job`, `/v/{vin}/systems`,
`/v/{vin}/tests`, every one of the three new `/v/{vin}/scans/{id}` and
`/v/{vin}/scans/{id}/health` links this very page links to, `/vehicles`, `/modules`, `/recordings`
— **timed out** rather than returning any status. This happened on the throwaway single-process
dev server this review started, immediately after the Scans-list page itself had just rendered
correctly moments earlier. Caveat: this review's own script crashed with an unrelated CDP timeout
shortly after sweeping these links, so a transient resource/contention issue in the review's own
process cannot be fully ruled out as a confound — but the pattern (one 500, then total silence) is
also consistent with a single bad request (`/live`) leaving the server's single-process event loop
unable to answer anything further, which would be a real and serious finding if confirmed.
**Fix:** re-run a clean, isolated dead-link sweep against a freshly started server (no concurrent
CDP session in the same process) hitting `/live` first in isolation, then the rest, to separate
"one route 500s" from "one route 500s and wedges the server."
**Accept when:** a dead-link sweep of `/v/{vin}/scans` returns real statuses (2xx/3xx/4xx, not
timeouts) for all 40 links, and `/live`'s own 500 (if still real) is fixed or explained.

## Not reached in this run (no finding, not a pass)

- **Scan detail** (`/v/{vin}/scans/{id}`) — freeze-frame tables per PID, Mode 06 table, exports
  (JSON/MES), the inline "Compare with previous scan" block, and the dedicated
  `/v/{vin}/scans/diff` page (its template, `scan_diff.html`, was confirmed to exist on disk by
  the time work resumed, but its live rendering was never exercised).
- **Health report** (`/v/{vin}/health`, `/v/{vin}/scans/{id}/health`) — verdict/25-system
  table/issues-in-order/"Do not clear"/no-"proven" checks.
- **Guided scan wizard** (`/v/{vin}/scan`) — idle → pause_blue → skip → pause_grey → skip →
  remove_cable → summary walk, and the "Open in Scans"/"Health report" links off the summary.
- **Live board freeze-frame panel** — Start/Stop/Save/Discard, unsaved-state wording, "open in
  Scans" link.
- **Bench/Report/Scans/Health cross-consistency** (same codes, same verdict across surfaces).
- **Job step 7 Mode 06 picker** (evidence offered from tonight's Mode 06 read).
- **`/m/{vin}` History** edit/delete(soft)/undo.
- Any 390×844 pass (only 768×1024 was captured before the interruption).

## Priorities
- **P0:** none confirmed (most scope unreached).
- **P1:** N2 (dead-link/timeout mass-failure on the Scans page — needs an isolated re-check).
- **P2:** N1 (resume card's two unexplained "how old" numbers).

## Regression tests to add
1. N2: an isolated dead-link crawl of `/v/{vin}/scans` against a freshly started server (no other
   concurrent client in the same process), asserting every linked route returns a real status
   within a few seconds — specifically re-checking whether `/live` 500ing correlates with
   subsequent requests timing out.
2. N1: assert the Bench resume card's "last scan ... ago" language and the scan id/timestamp named
   in the same card never disagree by more than the normal read lag, or that each date carries a
   label saying what it measures.
3. Re-run this review's full scope (scan detail incl. exports/diff, health report, wizard,
   freeze-frame panel, job step 7, `/m/{vin}` history) end to end without interruption — the
   orchestrator script and fake-ops harness built for this pass are reusable as-is.

## Data left on this VIN
None on the real car record. This run's server used a throwaway `CUORE_STATE_DIR` seeded from a
*copy* of tonight's real observations, never the live `:5000` instance or COM3; the one HTTP 500
on `/live` was against this throwaway server, not production.
