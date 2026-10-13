# CUORE — E2E re-test #3: Tests, Systems (map + dive-in), Liveboard

**Tested:** `/v/ZASFAKPN5J7B88115/tests`, `/v/ZASFAKPN5J7B88115/systems`,
`/v/ZASFAKPN5J7B88115/systems/evap` (+ `network`, `fuel`),
`/v/ZASFAKPN5J7B88115/liveboard` — the Stelvio, chronic P0440/P0455/P0456 — on
2026-10-13, against a throwaway `CUORE_STATE_DIR` and a server started for this
review only (never the live `:5000` instance). Headless Edge, one instance,
one tab, 768x1024 then re-navigated at 400x800 via CDP viewport override (no
second browser launch). 8 screenshots taken. Format follows
`JOB_UX_FIXES_RUN2_2026-10-08.md`; scope follows `SYSTEMS_DIVE_IN_PLAN_2026-10-08.md`.

## What passed

- **No 500s.** All 6 base pages (`tests`, `systems`, `systems/evap`,
  `systems/network`, `systems/fuel`, `liveboard`) returned 200 with no
  Traceback/Jinja2 error markers.
- **Dead-link sweep.** Every `<a href>` on all 6 pages was followed once
  (336 links total, including same-page and cross-page `#fragment`
  targets checked against the destination page's real `id=`/`name=`
  attributes). 335/336 resolved; the one break is below (F1).
- **Test result → Job step 7 evidence.** Opened a case, added an EVAP
  hypothesis by hand, posted a FAIL result on `esim_vacuum_test_a` with
  `hypothesis_id`/`supports=for` from the Tests surface's own result form,
  then loaded `/job?step=7`: the reason text and the linked evidence both
  appear on the step 7 hypothesis card, exactly as `tests_bridge.record_result`
  → `jobs_bridge.add_test_evidence` promises. This is the one explicit
  cross-surface contract in scope and it holds.
- **Co-occurrence wording.** Checked body text on the map and all 3 system
  detail pages for "depends on" vs "seen together on this car": the map's
  10 "depends on" instances are all genuine structural-dependency edges
  (the template's own `<b>Depends on:</b>` for `c.depends_on`); every hot/
  co-occurrence edge on `network`'s detail page (the only one of the 3 with
  a hot edge in this corpus) reads "seen together on this car"; zero
  instances of "depends on" applied to a co-occurrence-only edge anywhere.
- **Systems map Snapshot is honest.** With no scanner connected and no live
  session, clicking Snapshot on `/systems` refuses and shows "No live
  readings to snapshot yet." — no fabricated reading, no fake snapshot id.
- **Liveboard Start is honest** (if raw). With no adapter, Start surfaces
  the real underlying error rather than pretending to connect: `could not
  open port 'COM3': FileNotFoundError(...)`. True, just blunt (see F6).
- **UNKNOWN markers present and attested-input flow works.** The EVAP
  page's unattested facts (5 of them) each carry the `☐` toggle,
  "Add what you measured / add a source / add a photo" prompt, and the
  form posts to `/api/attested/{vin}` with a visible "SINGLE-SOURCE
  (mechanic)" chip on save — never entering the evidence gate as a car
  measurement, matching the page's own footnote.
- **Section count exceeds the plan.** Each system page renders 10
  `<details class="sysd-section">` blocks (Status, Relationships,
  Components, How it fails here, Hypotheses, What this car has taught,
  Others' experience, What else to look at, Learned DIDs, Freeze frame) —
  the original 8-item plan plus Phase 3/4's two additions, all present on
  `evap`/`network`/`fuel` alike.

## Findings

### F1 (P2). One dead "Record inspection →" link on the EVAP page
**Seen:** EVAP's Components section lists BCM among the placed electrical
elements and links `Record inspection →` to
`/v/.../electrical?system=evap#el-bcm`. That page returns 200, but BCM is
not tagged `evap` in the electrical layout, so `?system=evap` filters it out
and no `id="el-bcm"` exists on the page the link lands on — the anchor
silently does nothing. The other 4 elements on the same EVAP page (ECM,
ESIM connector, ESIM ground, purge valve connector) link correctly; this is
specific to components merged in as shared/gateway hardware whose own home
system differs from the page being viewed.
**Fix:** `system_detail_bridge.py` (line ~396) builds the href with
`#el-{eid}&system={first tag}`; when the element's own tags don't include the
viewed system, either drop the `?system=` filter from that link (show it
unfiltered) or add the viewed system to the query so the filtered page still
renders the element.
**Accept when:** every `Record inspection →` link on every system page lands
on a page containing a matching `id="el-*"`.

### F2 (P1). Vehicle name regresses to "(unnamed vehicle)" on exactly the new surfaces, and can poison other pages
**Seen (clean, deterministic, repeated twice):** on a freshly started server,
calling `/`, `/tests`, `/systems`, `/dossier`, `/systems/evap`, `/liveboard`,
`/job?step=7` in that order: `/`, `/systems`, `/dossier`, `/job` correctly
show "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir"; **`/tests`, `/systems/evap`
and `/liveboard` show "(unnamed vehicle)"** in both the `<title>` and the
vehicle bar — same empty `identity.vehicle` from the identical
`mes_bridge.workup(vin=vin)` call, same cache key, same process.
**Also seen (full interactive session, browser-driven, warm fetches hitting
`/tests` before anything else):** in that ordering, *all six* pages including
the map showed "(unnamed vehicle)" throughout the session — so the breakage
is not confined to the three routes above; visiting one of them first can
carry the empty name forward into pages that resolve it correctly when
visited first.
**This is the same defect as `JOB_UX_FIXES_RUN2` item #9** ("the Job page
still says (unnamed vehicle)... while Bench says Alfa Romeo Stelvio..."),
not yet fixed, now reproducible on three more surfaces and order-dependent.
**Fix:** trace why `tests_routes.py`/`system_routes.py`/`liveboard_routes.py`
(identical `_dossier(vin)` → `_vehicle_bar(vin, dossier)` call as
`bench_routes.py`) sometimes get an `identity.vehicle` that `bench_bridge`/
`dossier_bridge`/the map's `_build_view` resolve correctly from the same
corpus. `cache.get_or_build(("workup", vin, mtime), ...)` is shared across
all these call sites — whichever one runs first determines what the rest of
the process sees, which is the order-dependence above.
**Accept when:** `/tests`, `/systems/{key}`, `/liveboard` each independently,
as the *first* request against a cold server, show the real vehicle name —
mirroring `check_bench.py`'s own existing assertion.

### F3 (P1). Liveboard's Snapshot button is not honest about an empty capture
**Seen:** with no scanner connected and no Demo run (`this.values` is `{}`),
clicking Snapshot on `/liveboard` still POSTs to `/api/live/snapshots`,
succeeds, and renders **"Snapshot saved" + a real id** (`snap_20261013-152524_e76b1a87`
in this run) with no channel count, no recommendation rows, and nothing
telling the mechanic it captured zero channels. The Systems map's own
Snapshot button, under the identical no-scanner/no-session condition, does
the opposite and correctly refuses ("No live readings to snapshot yet.") —
so the same situation is handled honestly on one surface and dishonestly
(a silent, empty "success") on the other.
**Fix:** `liveboard.js`'s `LiveboardApp.prototype.snapshot` (line ~592) has
no guard the way `systems_map.js`'s `takeSnapshot` (line ~344) does; add the
same `Object.keys(this.values).length === 0` check and refuse with the same
honest message before POSTing.
**Accept when:** Liveboard Snapshot with zero live values refuses the same
way the Systems map's does, and a snapshot that does save always shows how
many channels/recommendations it actually captured.

### F4 (P1). Readability floor still broken, now on the new surfaces
**Seen (measured via `getComputedStyle(...).fontSize)`, 768px and 400px
alike):** `.ts-cat-chip`/`.ts-state-chip` (Tests, every row) render at
**11px** — 38 rows × 2 chips = 76 instances on the Tests page alone;
`.ts-conf-chip` (pass-criteria confidence badges, inside each row's Details)
at **10.5px** — 28 "unknown" + 13 "single_source" + 6 "corroborated" = 47
more; `.sys-card .subhead` and `.sys-legend-row` at **11.5px** on the map
(the legend's narrow-width media query makes this *worse*, not better, at
400px); `.lb-chan-band` (the known-good band line under every Liveboard
channel, shown even with nothing connected) at **11px** × 14 visible rows.
This is the same open item as `JOB_UX_FIXES_RUN2` #14 ("~80 text elements at
10–12px"), not fixed, now present on three more surfaces.
**Fix:** raise `tests.css` `.ts-cat-chip`/`.ts-state-chip`/`.ts-conf-chip`,
`systems.css` `.sys-card .subhead`/`.sys-legend-row`, and `liveboard.css`
`.lb-chan-band` to 12px minimum.
**Accept when:** a full-page `getComputedStyle` sweep of visible text on
these three surfaces returns zero elements under 12px, at both 768px and
400px.

### F5 (P2). Touch targets under 44px, concentrated in two places
**Measured via `getBoundingClientRect()` on every visible `a`/`button`/
`input`/`select`/`summary`/`[role=button]`/`label`:**

| Page | Viewport | Targets | <44px |
|---|---|---|---|
| Tests | 768 | 581 | 261 |
| Tests | 400 | 574 | 253 |
| Systems (map) | 768 | 162 | 72 |
| Systems (map) | 400 | 155 | 56 |
| EVAP detail | 768 | 139 | 54 |
| EVAP detail | 400 | 122 | 46 |
| Network detail | 768 | 95 | 19 |
| Fuel detail | 768 | 60 | 19 |
| Liveboard | 768 | 26 | 15 |
| Liveboard | 400 | 19 | 7 |

A large share of these are the app's shared nav bar (`Start`/`Vehicles`/
`Modules`/`Recordings`/`Logs` at ~20px tall) present on every page and out of
this review's scope. Two violations belong specifically to the surfaces
under test: **`.ts-filter-chip`** (Tests' All/Recommended/category filter
row) is `min-height: 36px` — under the 44px floor on every one of its ~13
chips; and the **Systems map's own tappable node links** (the thing the
legend explicitly invites: "Tap a node to open its full page") measure
**~47×24px** — the legend's promise of a tap target is true in width only,
not height.
**Fix:** raise `.ts-filter-chip` to `min-height: 44px` in `tests.css`;
enlarge the SVG node `<a>` hit area in `systems_svg.py` (a transparent
padding rect, not a visual resize) to at least 44px tall.
**Accept when:** both measure ≥44px on both axes via the same
`getBoundingClientRect` sweep.

### F6 (P2). Systems map's Live/Snapshot/slider depend on one silent-fail fetch
**Seen:** `systems_map.js`'s `init()` fetches `/api/systems/{vin}/state`
once; only on success does it append the Live toggle, Snapshot button, *and*
the session slider — on any failure (slow, error, non-200) it does nothing
and the comment says why: "the map still works unpainted -- never break the
page." That's the right instinct for the base map, but it means a slow or
failing endpoint silently removes three real features (Live overlay,
Snapshot, session slider) with zero indication to the mechanic that
anything is missing — no "Live overlay unavailable" message, nothing. Not
reproduced broken in this run (confirmed present once the fetch had time to
resolve — see note below), but the failure mode itself is silent by design.
**Note on this run's own false start:** my first read of the Live toggle
(checked immediately after navigation) found it missing, then the Snapshot
button (checked ~3s later, after the same fetch had time to land) worked
correctly — a timing artifact in this review's own script, not a confirmed
product bug, but it demonstrates exactly how invisible the failure state is:
nothing on screen distinguishes "not loaded yet" from "failed to load."
**Fix:** on a failed/slow fetch (e.g. >3s or a non-200), show a small
"Live overlay unavailable" note near the map rather than silently omitting
the controls.
**Accept when:** a forced-failing `/api/systems/{vin}/state` shows that
message instead of nothing.

### F7 (P2). Dependency-graph SVG is clipped at 400px with no visible scroll hint
**Seen:** at 400px the graph's own wrap (`overflow-x: auto` on
`.sys-graph-wrap`, correctly scoped so it never causes page-level horizontal
scroll — confirmed `document.documentElement.scrollWidth === innerWidth` at
400px throughout) is wider than its container; EVAP and ADAS/sensors render
fully or partially outside the visible 400px frame with no visible
scrollbar, edge fade, or other hint that more nodes exist to the right.
Functionally reachable by a horizontal swipe; nothing on screen says so, and
EVAP — the system actually under diagnosis on this car — is one of the
nodes cut off.
**Fix:** a small `--> scroll for more` affordance or edge-fade on
`.sys-graph-wrap` when its scrollWidth exceeds its clientWidth.
**Accept when:** that hint shows at 400px and disappears at widths where the
graph fits.

## Priorities
- **P0:** none found.
- **P1:** F2 (vehicle name), F3 (Liveboard Snapshot honesty), F4 (readability floor).
- **P2:** F1 (dead BCM link), F5 (touch targets), F6 (silent map-overlay failure), F7 (400px graph clipping).

## Regression tests to add
1. Extend `check_bench.py`'s "vehicle name is never (unnamed vehicle)"
   assertion to `/v/{vin}/tests`, `/v/{vin}/systems/{key}`,
   `/v/{vin}/liveboard`, each hit as the *first* request on a cold server
   (F2) — and a second variant that hits `/tests` first, then asserts
   `/systems` (map) still resolves the name, to catch the cross-page
   poisoning.
2. Liveboard Snapshot with `this.values == {}`: assert it either refuses
   (mirroring the map's message) or its result explicitly shows "0 channels
   captured" (F3).
3. A `getComputedStyle` sweep for font-size < 12px on `/tests`,
   `/systems/{key}`, `/liveboard` at both 768px and 400px, asserting zero
   matches (F4).
4. A `getBoundingClientRect` sweep for `.ts-filter-chip` and the systems
   map's `a[data-system]` nodes, asserting both axes ≥ 44px (F5).
5. A crawl of every system detail page's `Record inspection →` href against
   its destination page's real `id="el-*"` set, for all 25 system keys, not
   just EVAP (F1) — this run's generic dead-link sweep only caught it
   because EVAP happened to have a shared-hardware element.
6. Test → Job step 7 evidence (already passing, worth locking in): open a
   case, add a hypothesis, post a Tests-surface result with
   `hypothesis_id`, assert the reason text and evidence both land on
   `/job?step=7` without a reload — same shape as this run's manual check.

## Data left on this VIN
Job `c9ba5c6497bb` (technician "mech_review_3"), hypothesis `54be0ac2`
("mech_review_3: cracked EVAP purge line hypothesis", system evap, codes
P0455/P0440), and a FAIL 0.3 result on `esim_vacuum_test_a` with reason
"mech_review_3 smoke leak" — all against the throwaway `CUORE_STATE_DIR`
this review created, not the live server. Nothing to clean up.
