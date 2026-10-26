# GitHub tools survey for CUORE (2026-10-26)

**Purpose:** open-source projects that could help CUORE's development. Research only: nothing
was installed, cloned or run. **Verdicts:** ADOPT / EVALUATE / REFERENCE ONLY / AVOID.
**Caveats:** Part 1 is built from CUORE's own earlier GitHub reviews
(`docs/research/GITHUB_REVIEW_GIORGIO.md`, `GITHUB_REVIEW_TOOLING.md`,
`EXTERNAL_IMPLEMENTATION_REVIEW.md`, `external/README.md`, pages read 2026-10-20); rows marked
[BG] are background knowledge, unverified (stars, dates, licences to be checked). In Part 2,
last-commit dates were not visible and some licences/stars were not shown.

## Part 1 - Diagnostics, CAN and UDS

| Project | Licence | Verdict | What it does for CUORE |
|---|---|---|---|
| commaai/opendbc `fca_giorgio.dbc` | MIT | ADOPT (already vendored in `cuore/data/dbc/`) | The only Giorgio CAN-CH signal database; feeds `chassis_decode.py` / `dbc.py`. Scales unverified on this car: validate with CUORE captures. |
| pylessard/python-udsoncan | MIT (pushed 2026-09-21) | EVALUATE | Offline test oracle for P2/P2*/0x78 handling in `uds.py` via its FakeConnection. No ELM class, so it does not replace CUORE's code. |
| pylessard/python-can-isotp | MIT | REFERENCE ONLY | Flow-control timing and 29-bit addressing checks; needs a python-can bus, which an ELM/STN adapter does not give. |
| cantools [BG] | MIT | EVALUATE | Dev-only cross-check of `dbc.py` decoding. |
| SavvyCAN [BG] | MIT | EVALUATE | Offline viewing/diffing of bus-capture recordings and DBC tests. |
| tr3ma-crew/BACCAble-firmware | mixed, no explicit grant for its own code | REFERENCE ONLY | Bus ids by network (C1 = CAN-C, C2 = CAN-CH, BH = CAN-IHS) and likely addresses (IPC 0x60, ABS 0x28, RFHUB 0xC7). 0x18DABAF1 is its internal route-request id (unverified): CUORE never targets BA and keeps RFHUB read-only. It injects frames onto the car: never run it or copy its code. |
| python-OBD | GPL-2.0 | REFERENCE ONLY | Its Mode 06 parser can cross-check `mode06.py`. |
| ELM327-emulator | CC BY-NC-SA | REFERENCE ONLY | For test fakes prefer CUORE's own recordings through `replay.py` (licence). |
| caringcaribou | GPL-3.0 | REFERENCE ONLY | Timing and DID-discovery ideas; it sends scanner traffic, never run it on the car. |
| CANalyzat0r, cracked AlfaOBD repos | - | AVOID | Unsafe / unlicensed. |
| ClaudeMarais/AlfaRomeoGiulia_DashboardInfo_ESP32-S3 | CC BY-NC 4.0 | REFERENCE ONLY | ECM DIDs for a 2019 2.0 petrol: a lead for DID confirmation. |

No Stelvio-specific DID lists, PROXI decoders or wiTECH-free tools were found.

---

## Part 2 - Interface and workshop tooling


Method: WebFetch of GitHub repo pages. GitHub pages did not show last-commit dates or release dates (Releases panels came back empty), so "last commit" is NOT VERIFIED for any row; stars and licences are as seen. Rows marked (knowledge) rely on prior knowledge, not a page fetched today. Verify version/date on the repo before adopting. All are free/open source; none paid.

## Table

| # | Candidate | URL | Stars (seen) | Licence | Weight | What it does for CUORE | Risk | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | htmx | https://github.com/bigskysoftware/htmx | 49.6k | not shown on page; BSD-0 / permissive (knowledge) | ~14 KB min+gz, single file, zero deps, vendorable | Partial swaps on procedure pages: Start/Continue step buttons post and swap a "step card" fragment; polling (hx-trigger="every 1s") for readings tiles as simplest live feedback; STOP button as hx-post with hx-sync to abort in-flight; hx-confirm not used for hold-to-confirm (see #7) | Two major lines (2.x vs newer); pin one file in /static. Out-of-band swaps can hide state bugs | ADOPT (vendored in /static, no CDN) |
| 2 | htmx extensions (sse, ws) | https://github.com/bigskysoftware/htmx-extensions | 284 | not shown on page (knowledge: permissive) | small JS files, vendorable | sse ext: swap live reading tiles and step status from a server event stream; ws ext only if bi-directional channel is needed | Extensions repo is separate from core; check it matches pinned htmx version. Reconnect behaviour must be tested on tablet Wi-Fi sleep | EVALUATE (SSE yes; skip ws) |
| 3 | sse-starlette | https://github.com/sysid/sse-starlette | 855 | BSD-3-Clause | pure Python, tiny; works with Starlette/FastAPI (EventSourceResponse) | Server side of live readings: one /procedure/{id}/events stream pushing reading + step-state + result events; disconnect detection to trigger safe abort | Single COM3 adapter: stream must read from CUORE's session layer, never open its own adapter contact (per no-raw-adapter rule). Client disconnect must NOT leave an actuator active: server-side watchdog needed regardless | ADOPT (or write 30 lines by hand; EventSourceResponse is the safer choice) |
| 4 | Alpine.js | https://github.com/alpinejs/alpine | 32.0k | MIT | ~15 KB gz (knowledge), one file | Local-only UI state: hold-to-confirm progress, dialog open/close, collapsible panels, theme toggle, unit toggle. Replaces ad-hoc inline scripts with declarative x-data | Another dependency overlapping what ~40 lines of vanilla JS can do; CSP build needed if strict CSP | EVALUATE (vanilla JS is enough for hold-to-confirm; Alpine only if inline scripts multiply) |
| 5 | uPlot | https://github.com/leeoniya/uPlot | 10.6k | MIT | ~50 KB min, zero deps, canvas | Recording viewer and live graph: tens of thousands of points, zoom/cursor sync across several parameters (rpm vs trim vs lambda). Faster than SVG paths for long drive recordings | Canvas not SVG: loses server-side-rendered determinism, harder to headless-screenshot-diff; touch zoom needs tuning; style to the bay-tablet theme. Keep CUORE SVG charts for short static report charts and print/PDF | EVALUATE (use only for long recordings / live scrolling graph; keep SVG for reports) |
| 6 | Chart.js | https://github.com/chartjs/Chart.js | 67.8k | MIT | larger than uPlot (~200 KB min, knowledge), canvas | General charts | Heavy, animation-oriented, poor fit for dense time series | AVOID (uPlot or own SVG is better fit) |
| 7 | Hold-to-confirm: no library | (pattern) | - | - | ~40 lines vanilla JS + CSS | Pointer events (pointerdown start timer, pointerup/leave/cancel resets), CSS fill animation on a >=44 px button, 1.0-1.5 s hold, keyboard equivalent (Space held), aria-live "Hold to confirm", server also requires a one-time token so a stray POST cannot fire an actuator | None beyond testing on the real tablet (touch long-press can trigger context menu: set touch-action:none, -webkit-touch-callout:none, user-select:none, preventDefault on contextmenu) | ADOPT as in-house component; no maintained tiny GitHub library found worth a dependency |
| 8 | Native <dialog> + popover | (web platform; MDN) | - | - | zero | Confirm dialogs, "result recorded" sheets, big STOP overlay. Built-in focus trap, Esc, ::backdrop; works offline, no JS library | Old tablet browsers: check <dialog> support on the actual tablet | ADOPT |
| 9 | Playwright for Python | https://github.com/microsoft/playwright-python | 15.1k | Apache-2.0 | Python pkg + downloaded browser (hundreds of MB); can use installed Chrome via channel="chrome" | Replaces ad-hoc headless-Chrome screenshots: viewport = tablet size, dark/light, wait-for-selector, locator-based clicks on procedure pages, tests of SSE updates, hold-to-confirm (mouse.down/wait/up), expect(...).to_have_screenshot() visual baselines | Install is a "do not install" item for this research; pip + browser download is a one-time dev-machine step. Pixel baselines flake across OS/fonts: pin one machine, mask dynamic regions. Plain-script tests are CUORE style: Playwright sync API fits plain scripts, pytest not required | ADOPT (dev-only, never on the bay tablet) |
| 10 | pytest-playwright / snapshot plugins | https://github.com/microsoft/playwright-pytest | (not fetched) | Apache-2.0 (knowledge) | pytest dep | Fixtures and visual-snapshot helpers | CUORE tests are plain scripts, adding pytest changes style | REFERENCE ONLY (Playwright's own sync API suffices) |
| 11 | axe-core | https://github.com/dequelabs/axe-core | 7.7k | MPL-2.0 (file-level copyleft: fine to use unmodified as dev tool) | one JS file, bundled in the npm/pip wrappers | Automated checks on every page: contrast in dark and light themes, missing labels on icon buttons, target-size, aria on dialogs. Run in the Playwright suite | MPL-2.0 is weak copyleft; keep it dev-only, not shipped. Automated checks catch only part of accessibility | ADOPT (dev-only) |
| 12 | axe-playwright-python | https://github.com/pamelafox/axe-playwright-python | 31 | MIT | small wrapper | Convenience axe.run(page) from Python | Tiny project, single maintainer, did not confirm offline bundling. Alternative: read axe.min.js from the axe-core package and page.add_script_tag(path=...) yourself | EVALUATE (or do the 5-line add_script_tag approach) |
| 13 | Workbox | https://github.com/GoogleChrome/workbox | 13.0k | MIT | generator/CLI tooling (Node) | Service-worker precache of /static assets | README notes ownership moving to Chrome's Aurora team. Needs Node build step CUORE does not have; CUORE is served from the bay laptop/LAN, not the internet | AVOID (hand-write ~50-line service worker if ever needed) |
| 14 | Hand-written service worker + manifest | (pattern) | - | - | ~50 lines | Only relevant if the tablet loads CUORE from a LAN server and the server may drop: cache app shell (CSS, JS, fonts, icons), show "server unreachable" banner and last-known procedure state. Note: a service worker needs HTTPS or localhost; LAN http IP does NOT qualify | Cached stale pages near an actuator test are a safety hazard: never cache procedure/action routes, never replay queued POSTs | EVALUATE (app-shell only; never cache actions) |
| 15 | canvas-gauges | https://github.com/Mikhus/canvas-gauges | (not fetched) | MIT (knowledge) | no deps, canvas | Radial/linear gauge look for live tiles | Canvas, animated; CUORE already draws SVG | REFERENCE ONLY (look/feel inspiration) |
| 16 | Hudiy OBD gauge examples | https://hudiy.eu/community/viewtopic.php?p=212 (links to vendor GitHub examples) | n/a | unknown | HTML/JS | Example HTML displays over ELM327 | Vendor-specific platform, licence unconfirmed | REFERENCE ONLY |
| 17 | piObdDashboard | https://github.com/brian03079/piObdDashboard | not fetched | not verified | Python Pi app | Layout ideas for speed/rpm/throttle display | Not verified, hobby scale | REFERENCE ONLY |
| 18 | ReDrive | https://oosmetrics.com/repo/iUnreallx/ReDrive | not fetched | not verified | Flutter app | Live-data and DTC screen layouts | Native app, different stack | REFERENCE ONLY |
| 19 | PriiDash | https://priidash.sourceforge.net/ | n/a (SourceForge) | not verified | Old | Layout ideas only | Dated | REFERENCE ONLY |

## Notes

Fit with CUORE principles
- Everything above marked ADOPT is vendorable as one file in /static (htmx, optional Alpine, uPlot): no CDN, works offline. Pin the exact file and record its sha256 in the repo.
- Live feedback design that needs only #1-#3: procedure page loads server-rendered; an SSE stream (sse-starlette) emits named events (reading, step, result, stopped); htmx sse extension swaps the tiles. If the extension proves flaky, 15 lines of native EventSource JS do the same job and need no library at all; EventSource is built in and auto-reconnects.
- Safety does not live in the browser. STOP must be a plain form POST that works even if JS or SSE fails (big red button, 44 px+ minimum, preferably 72 px), the server must also stop the actuator on stream disconnect or heartbeat timeout, and hold-to-confirm must be backed by a server one-time token. Auto-record the result on the server when the step ends (any of ok/abort/stop/timeout), not from client JS.
- Polling vs SSE: for a 1 Hz readings tile, htmx polling is simplest and most robust; use SSE when step transitions must feel instant. Note the single-adapter constraint: one server-side reader fans out to all viewers.
- Charts: keep CUORE SVG for reports (deterministic, screenshot-testable, printable). Consider uPlot only when a recording exceeds roughly 5-10k points or when pinch-zoom/cursor sync is wanted. Decide with a measured test on the tablet before adopting.
- Testing: Playwright (Python, sync API) drives the same flows a mechanic does: set viewport to the tablet, toggle theme, hold the confirm button, assert the result row appears, run axe. Use `channel="chrome"` to reuse the installed Chrome and avoid a separate browser download. Visual baselines: one pinned machine, masked timestamps/live values. Against the design spec, assert computed sizes (>=44 px targets, >=16 px text) with locator.bounding_box() and evaluate(getComputedStyle): cheap, deterministic, and no extra tool needed.
- Offline: CUORE is likely served on the same LAN/host as the tablet, so "offline" mostly means no external CDN, fonts or icon fonts. Check that the design spec uses system fonts or bundled WOFF2. A service worker is optional and low value; secure-context rules (HTTPS/localhost only) make it awkward on a plain-http LAN address.

Caveats
- Last-commit and release dates were not visible on the fetched GitHub pages, so maintenance activity is unconfirmed for every row. Before adopting, open the Releases/Commits page and the issue tracker.
- htmx licence and extension licence were not shown on the fetched pages; check the LICENSE file (htmx core is widely known as BSD 0-clause, from knowledge).
- Gauge/dashboard projects were found via search only; none were opened; treat as inspiration, check licence before copying any code or assets.

## Sources
- https://github.com/bigskysoftware/htmx
- https://github.com/bigskysoftware/htmx-extensions
- https://github.com/sysid/sse-starlette
- https://github.com/alpinejs/alpine
- https://github.com/leeoniya/uPlot
- https://github.com/chartjs/Chart.js
- https://github.com/microsoft/playwright-python
- https://github.com/dequelabs/axe-core
- https://github.com/pamelafox/axe-playwright-python
- https://github.com/GoogleChrome/workbox
- Web search: open source car dashboard gauges (hudiy.eu community, github.com/brian03079/piObdDashboard, priidash.sourceforge.net, Mikhus/canvas-gauges, ReDrive)

---

## Recommended next steps

1. Adopt **htmx** and **sse-starlette** for the interactive procedures (vendored in `/static`, no CDN; CUORE runs offline).
2. Build hold-to-confirm and STOP in-house (~40 lines); STOP as a plain form POST.
3. Adopt **Playwright for Python** and **axe-core** as dev-only test tools (flows, 44 px / 16 px, contrast in both themes).
4. Use **udsoncan** as an offline test oracle only; keep CUORE's own ISO-TP/UDS code.
5. Keep **opendbc** vendored and validate its scales against CUORE captures.
6. Evaluate **uPlot** for long recordings only after a tablet test; keep SVG charts for reports.
7. Never run tools that write to the car (BACCAble firmware, caringcaribou); avoid cracked tools.
8. Verify the [BG] rows (stars, licences, dates) before adopting any of them.
