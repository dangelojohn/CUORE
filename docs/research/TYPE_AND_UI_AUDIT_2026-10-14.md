# CUORE 0.1.0 — Typography, HTML & CSS audit + fix spec

**For:** Claude Code (implementation)
**Audited:** 2026-10-14, live app at `http://127.0.0.1:5000`, vehicle `ZASFAKPN5J7B88115`
**Method:** computed-style extraction (fonts, sizes, weights, contrast, overflow, tap targets, stacking) + screenshots, dark and light theme, at a **485 px viewport** (Chrome side-panel width — effectively the phone layout). Desktop ≥1024 px was **not** tested; re-run the verification script in §7 there after fixing.
**Layers covered:** global shell (header, vehicle strip, tab nav, footer, FAB), Bench, Job steps 1–12 + stepper + sticky bars, Record-result dialog, Hypotheses, Codes table, Code detail, Tests, Systems graph, Full scan, Liveboard, Report.

Stylesheets in play: `cuore.css` (492 rules), `flow.css`, `icons.css`, `print.css`, `fullscan.css`, `liveboard.css`, `feedback.css`, plus 3 inline rules. 675 rules total, **51 `!important`**.

---

## 0. Root causes (fix these first — they clear ~60 % of the symptoms)

| # | Root cause | Symptoms it produces |
|---|---|---|
| R1 | **No type scale.** 35 distinct `font-size` values in the CSS (8, 8.5, 9, 9pt, 10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 26, 28, 30, 32, 34, 36, 40, 44, 56 px, 0.85em, 0 px…). Half-pixel sizes. | Every page has its own hierarchy; same-role text differs between pages; H3 bigger than H2 context; 11 px meta text. |
| R2 | **`body` font-size declared 4 times** in `cuore.css` (15 px → 16 px → 16 px/1.6 → 17 px) and the **colour tokens declared 3 times on `:root`** (original blue-grey palette, then a later `--bg:#000; --surface:#0a0a0a; --ink:#fff…` override, then a lone `--ink-3:#9aa4ac`). | Mixed palettes: `--raised #262d33` and `--rule-soft` blue-greys sitting on pure black; impossible to reason about which value wins; light theme partially inherits dark decisions. |
| R3 | **Form controls don't inherit the font.** Only `.btn`, `.jump-chip`, `.hyp-status-btn`, `.tool-have-btn`, inputs of type text/search, textarea, select set `font-family: inherit`. | `<button>` elements (e.g. `button.step-check`, PASS/FAIL buttons on Tests, theme/print icon buttons), `input[type=number]`, radios, checkboxes render in **Arial 13.33 px** (31 Arial nodes on Job step 6). |
| R4 | **Absolutely-positioned hero text.** `.vhero .hero-text { position:absolute; top:-56.58px }` inside `.vhero-compact { overflow:hidden }`. | Bench: the vehicle name's first line ("Alfa Romeo Stelvio 2.0 Turbo 16V") is clipped — only "MultiAir" shows. Report: the hero verdict + figures ("0 OPEN CODES / 142,289 / 94 %") paint **over the site header**. |
| R5 | **Header has `z-index:20` but `position:static`**, so the z-index is ignored; `.vbar` (z 15) stacks above it. | Same as R4 on Report; header icons visibly overlapped. |
| R6 | **Rows that never wrap.** The vehicle strip (`.chip.plain`, `.chip-verdict`, `details.vmore`, `.vmore-tab`) and tab nav are `nowrap` with no overflow container. | `document.scrollWidth` = **575 px** (Bench/Scan) and **694 px** (Job) at a 485 px viewport → whole page scrolls sideways; "Live…" link cut; `scrollIntoView` on a row pans the page left by ~120 px (observed when opening Record-result). |
| R7 | **Two sticky bars share `top:0`.** `.vline` (z 15, 49 px) and `.flow-bar` (z 14, 45 px) both `position:sticky; top:0`. Plus sticky `.step-nav` (bottom, 65 px) and fixed `.fab-feedback` (z 40). | First line under the bars is hidden ("1/25 test result(s) recorded" is cut); FAB sits on top of the **Next** button and on top of the last word of most right-aligned text. |
| R8 | **Monospace used as a semantic marker for whole sentences** (evidence items, citations, tool lists, footer, timestamps, legend items). | 84+ mono text nodes per page; full English sentences in `ui-monospace` bold read poorly and wrap badly. |

---

## 1. Proposed foundation (put in `cuore.css` top, delete the duplicates)

Replace all three `:root` token blocks and all four `body` rules with **one** block per theme. Keep the existing semantic token *names* so the rest of the CSS keeps working.

```css
/* ---------- 1. TYPE ---------- */
:root{
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SFMono-Regular", "Cascadia Mono", Menlo, Consolas, "Liberation Mono", monospace;

  /* Scale: 7 steps, nothing else allowed */
  --fs-xs: 0.75rem;   /* 12px  caption, badges, table meta (absolute minimum) */
  --fs-sm: 0.875rem;  /* 14px  secondary text, labels, chips, table body */
  --fs-md: 1rem;      /* 16px  body, inputs (16 = no iOS zoom) */
  --fs-lg: 1.125rem;  /* 18px  lead / card titles / h4 */
  --fs-xl: 1.25rem;   /* 20px  h3 */
  --fs-2xl: clamp(1.375rem, 1.1rem + 1vw, 1.625rem); /* 22–26px h2 */
  --fs-3xl: clamp(1.75rem, 1.3rem + 2vw, 2.25rem);   /* 28–36px h1 / hero */

  --lh-tight: 1.2;    /* headings, hero */
  --lh-snug: 1.35;    /* chips, buttons, table cells, cards */
  --lh-body: 1.55;    /* paragraphs */

  --fw-regular: 400;
  --fw-medium: 500;
  --fw-semibold: 600; /* replaces every 650 */
  --fw-bold: 700;     /* numbers/emphasis only */

  --tracking-caps: 0.06em; /* ONE value for all uppercase labels */
  --mono-scale: 0.92em;    /* inline mono optically matches sans */

  /* spacing / shape (already partly present – unify) */
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:24px; --space-6:32px; --space-7:48px;
  --radius-sm:4px; --radius:8px; --radius-pill:999px;
  --tap: 44px;
}

html{ font-size:100%; -webkit-text-size-adjust:100%; text-size-adjust:100%; }
body{
  margin:0; font-family:var(--sans); font-size:var(--fs-md); line-height:var(--lh-body);
  color:var(--ink); background:var(--bg);
  font-kerning:normal; text-rendering:optimizeLegibility;
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
}
button, input, select, textarea{ font:inherit; color:inherit; letter-spacing:inherit; }  /* fixes R3 */
h1,h2,h3,h4{ line-height:var(--lh-tight); text-wrap:balance; margin:0 0 var(--space-3); }
p, li, dd{ text-wrap:pretty; }
h1{ font-size:var(--fs-3xl); font-weight:var(--fw-semibold); letter-spacing:-0.01em; }
h2{ font-size:var(--fs-2xl); font-weight:var(--fw-semibold); }
h3{ font-size:var(--fs-xl);  font-weight:var(--fw-semibold); }
h4{ font-size:var(--fs-lg);  font-weight:var(--fw-semibold); }
small,.small{ font-size:var(--fs-sm); }
code,kbd,samp,.mono{ font-family:var(--mono); font-size:var(--mono-scale); font-variant-ligatures:none; }
.num,td.num,.mono,time{ font-variant-numeric:tabular-nums; }
.caps{ text-transform:uppercase; letter-spacing:var(--tracking-caps); font-size:var(--fs-xs); font-weight:var(--fw-semibold); }
```

**Rules for the codebase going forward** (add as a comment block in `cuore.css`):
1. No raw `font-size` in px anywhere except inside `:root`. Use `var(--fs-*)`.
2. No `font-weight` other than 400/500/600/700. Search-replace `650` → `var(--fw-semibold)`. Drop `300` (light weight is used for H1/H2 "Full scan", "Open work", "Edge detail", "Verdict", "7. Hypotheses" — it reads as *disabled* on black and fails emphasis).
3. Monospace only for: DTC codes, part numbers, VINs, bulletin IDs, raw values+units, keyboard keys. **Never** for sentences.
4. Uppercase only via `.caps` and only for ≤3-word labels.
5. Minimum rendered text: 12 px. Minimum interactive height: 44 px (`--tap`).

### Colour tokens — one dark, one light

Pick **one** dark palette. Current state mixes neutral black (`#000/#0a0a0a/#111`) with blue-grey leftovers (`--raised #262d33`, `--ink-2 #b8bec4`). Recommendation: keep the neutral override (it is what users see) and re-derive the remaining tokens from it:

```css
:root{ color-scheme:dark;
  --bg:#000; --surface:#0b0c0d; --surface-2:#141617; --raised:#1d2022;
  --rule:#2a2d30; --rule-soft:#1c1f21;
  --ink:#f2f4f5; --ink-2:#b9c0c5; --ink-3:#8f99a1;   /* ink-3 ≥ 4.5:1 on --surface-2 */
  --accent:#e8565c; --accent-ink:#1a0506;            /* text ON accent: dark, see C1 */
  --accent-dim:#3a1e20; /* sev-*, ok, fam-* unchanged */
}
:root[data-theme="light"]{ color-scheme:light; /* existing light tokens, with: */ --ink-3:#5b656c; }
@media (prefers-color-scheme:light){
  :root:not([data-theme="dark"]){ color-scheme:light; /* same light tokens */ --ink-3:#5b656c; }
}
/* light --ink-3 was #68737a = 4.06:1 on --surface-2 #e8ebee (nav tabs, muted text fail AA); #5b656c = 4.98:1 */
```

Then delete the second and third `:root` blocks and the `:root{--ink-3:#9aa4ac}` straggler.

---

## 2. Global shell (every page)

**G1 — Brand wordmark reads "CU O RE".** `.brand{display:flex;gap:8px}` turns the text nodes `CU`, `<span>O</span>`, `RE` into three flex items with 8 px gaps.
*Fix:* wrap the word: `<span class="wordmark">CU<span class="wm-o">O</span>RE</span>`; keep `gap` only between logo and wordmark. `.wordmark{letter-spacing:0.08em;font-weight:var(--fw-bold);font-size:var(--fs-sm)}`.

**G2 — Placeholder logo shipped.** `.logo-slot` is a 32×32 dashed box with a "LOGO" background image. Replace with the real mark or hide the slot until one exists (`.logo-slot:empty{display:none}` once the bg image is removed).

**G3 — Header icon buttons use emoji / Unicode glyphs** (`◐`, `🖨`, `☰`). The printer is a colour emoji, renders faded in light theme and differently per OS; the theme toggle shows no state (same glyph in dark and light; first click appeared to do nothing — it may be cycling through "auto"). Icons render in Arial (R3), `line-height` 15/15.
*Fix:* inline SVG icons (`currentColor`, 20 px) from `icons.css`; theme toggle with `aria-pressed` and a sun/moon swap, plus a visible "Auto" state if 3-way.

**G4 — Vehicle strip overflows (R6).** `…J7B88115 142,289 km | Connect to car | Scanner: not running | Li…` exceeds the viewport.
*Fix:*
```css
.vline{ display:flex; flex-wrap:wrap; gap:var(--space-2); align-items:center; min-width:0; }
.vline > *{ min-width:0; }
.vmore-panel{ position:absolute; right:0; max-width:min(90vw,360px); }  /* currently left:454 → right:694 */
```
Scanner status chip in mono green on green looks like a success state although it says "not running" → use the neutral/once tone.

**G5 — "Connect to car" / all `.btn.primary`: white on `#e8565c` = 3.55:1** (fails AA for 13 px text). *Fix:* either darken accent for fills (`--accent-fill:#c7363d` → 5.2:1 with white) or use dark text on accent (`--accent-ink`). Apply to "Next: …" step buttons, liveboard "Start", codes filter "All" chip (`a.codesf-chip.on` also 3.55).

**G6 — Tab nav labels.** Uppercase, letter-spaced 0.98 px, and the label **`LIVE_BOARD` / `live_board`** is an identifier. Rename to "Live" (or "Live data"). Nav overflows horizontally with no affordance; make it `overflow-x:auto; scroll-snap-type:x mandatory;` with a fade mask, or collapse to a select below 520 px. Active tab currently only has a box; add a 2 px accent underline.

**G7 — Footer** (`CUORE 0.1.0 · profile bench · Simulation logs excluded… · ? keys · Developer API`) is 11 px mono; "Developer API" link is 84×13 px. Raise to `--fs-xs` sans, make links ≥44 px tall via padding.

**G8 — Floating feedback FAB `?/✎`** (fixed, z 40, bottom 18 px, 52 px) covers: the Next button on every job step, the right end of truncated lines (e.g. "(attested 14 Oct)", "Recommended: … P0456"), chips in the scan module table, and duplicates the bottom "Ask / correct (this page)" bar.
*Fix:* when `.step-nav` is present, lift the FAB: `.has-step-nav .fab-feedback{bottom:calc(65px + 16px)}`; add `padding-bottom:96px` to `main`; or fold the FAB into the step-nav as an icon button. Remove one of the two feedback entry points.

**G9 — Keyboard help heading** `H2 "Keyboard"` (26 px/300) is the only H2 on some pages and is hidden — screen readers get it as the page's main heading. Make it an `h2` inside a `<dialog>` that's not in the outline until opened.

**G10 — Heading outline.** Bench and Job pages have **no `<h1>`**; Job's step title is an H2, followed by a second H2 ("Open work") under a `<summary>` that says the same thing ("Open work & attachments"); section titles are H3 at 15 px while "Others' experience" is H3 at 19 px (bigger than its parent section). Bench card titles are `H4` at **12 px** (smaller than body).
*Fix:* one `h1` per page (vehicle name on Bench, "Step 6 · Tests & inspections" on Job); system groups `h2`; tests `h3`; drop the duplicate "Open work" heading.

**G11 — Page titles** say "(unnamed vehicle)" on Codes and Report while every other page has the model name. Use the same vehicle-name helper.

**G12 — Copy typography.** Double hyphens `--` used as dashes everywhere in UI strings ("not cleared, not resolved", "One tap deep -- tap…", "CAN-IHS (body / comfort) -- blue A5"). Plural hacks: "test result(s)", "hypothesis(es)", "piece(s)". Mixed date formats on one screen: `2026-10-13T20:03:00`, `13 Oct 20:03`, `11 h ago`, `2026-10-08 09:26:00`, `done 2026-10-14T07:58:26`.
*Fix:* a Jinja filter `|dash` (replace ` -- ` with ` — `), a `pluralize` helper, and a single `|when` filter: relative ("11 h ago") with an absolute `<time datetime title>` tooltip, absolute format `14 Oct 2026, 07:58`. Never render raw ISO with `T`.

---

## 3. Bench (`/v/<vin>`)

**B1 — Vehicle name clipped (R4).** Fix the hero as a normal-flow grid:
```css
.vhero{ position:relative; display:grid; overflow:visible; }
.vhero > *{ grid-area:1/1; }                 /* image and text share a cell */
.vhero .hero-text{ position:static; align-self:end; padding:var(--space-4); }
.hero-name{ font-size:var(--fs-3xl); font-weight:var(--fw-semibold); line-height:var(--lh-tight); text-wrap:balance; }
```
Test with the longest names in the fleet (the Stelvio wraps to 2 lines at 485 px).

**B2 — Hero ignores light theme**: stays black band with white text while the page turns light. Either intentional "photo band" (then add a scrim token `--hero-scrim` and keep text white everywhere) or theme it.

**B3 — Instruction callout** ("Open the codes and start the first test below.") 20 px bold centred with a `▸ Why?` disclosure jammed top-right. Make it left-aligned `--fs-lg`, put "Why?" as a text button under the sentence.

**B4 — Bench task cards**: checkbox centred in a left column with a caps "MARK DONE" label under it, title in a second column, status chip third. At 485 px the title wraps into 2 lines next to an unrelated label.
*Fix:* `grid-template-columns: var(--tap) 1fr auto;` checkbox top-aligned with title first line, drop "MARK DONE" label (use `aria-label`), part ref chip on its own line under the title.

**B5 — Status chips inconsistent**: `READY` (caps, green, mono), `BLOCKED: MES running` (mixed case, red, mono), `attempt — adapter not reachable` (lowercase, amber), `Scan 0 of 10` (mono box). Define one `.status` component: sans `--fs-xs`, `.caps`, semantic tone from `--sev-*`/`--ok`, never mono.

**B6 — Fuel gate / Readiness cards** use `H4 12px/600` titles smaller than their values (15 px). Swap: label `.caps --fs-xs --ink-3`, value `--fs-lg` semibold, timestamp `--fs-sm`.

**B7 — Parts / tools lines**: part numbers run inline inside a sentence (`04861961AD EVAP purge valve / solenoid · 68337662AC…`) and tool names are mono pills that wrap internally ("Hand-held vacuum pump (Mityvac-style, w/ gauge) — unknown: ask" in a pill over 2 lines).
*Fix:* render as a two-column definition list (name | P/N mono), tools as a plain list with an "unknown: ask" status chip, not a pill around the whole sentence.

**B8 — Code chip legend is non-functional.** Chips `P0456 B1040 P0455 C141B` are all the same amber, while the legend shows "Active" and "Cleared, unverified" as two identical neutral chips with no swatch. Colour chips by state using `--sev-*` and give legend items the same swatch.

**B9 — Secondary navigation buttons** ("Job", "Tests", "live_board", "System: EVAP…", "Full dossier") are 4 different widths, mixed case, identifier label. Make them a consistent link list or button group.

**B10 — Dangling separators**: "· 1 of 28 done", "· Scanner: Not running" begin with `·`. Use CSS `:not(:first-child)::before{content:"·"}`.

---

## 4. Job flow (`/job?step=N`)

**J1 — Sticky bar collision (R7).** `.vline` and `.flow-bar` both `top:0`.
```css
:root{ --vline-h:49px; }
.flow-bar{ top:var(--vline-h); }               /* or merge both into one bar */
main{ scroll-padding-top:calc(var(--vline-h) + 45px + 8px); }
html{ scroll-padding-top:calc(var(--vline-h) + 45px + 8px); }
```
Check the first line of each step is visible after navigation.

**J2 — Stepper.** Numbers-only buttons with labels in `title` (hover-only, unusable on touch); wraps 10–12 to a second row inside a horizontal scroller; phase labels (INTAKE / DIAGNOSE / REPAIR / CLOSE-OUT) don't align with their step groups; current step uses a large red outlined box while completed steps are only tinted digits; every item has `aria-current="false"` (remove; set `aria-current="step"` on the current one only).
*Fix:* one row, `display:grid; grid-auto-flow:column; grid-auto-columns:minmax(36px,1fr)`, phase labels as `grid-column: span N` above; show the current step's name under the row; done = filled dot, current = ring, todo = outline.

**J3 — Step header**: "6. Tests & inspections" H2 26/300 + "1/25 test result(s) recorded" 20/300 + "In progress 1/28" pill + "▼ Open work & attachments" summary + H2 "Open work" + red rule. Five stacked header elements before content.
*Fix:* `h1` step title (semibold), one meta line `--fs-sm --ink-2` ("1 of 25 results recorded · In progress"), remove the duplicate H2 and the red rule.

**J4 — System relation links** under each group ("EVAP (evaporative emissions) (primary) Electrical supply (upstream?) Fuel (upstream)") render as **17 px underlined running text**, and repeat (Body group shows "Network / CAN buses" and "Electrical supply" twice each). They are `a.sysb-chip` but styled as text, 23 px tall.
*Fix:* real chips — `--fs-xs`, pill, role prefix as a small caps tag (`PRIMARY`, `UPSTREAM?`), dedupe server-side, min-height 32 px with 44 px hit area.

**J5 — Code chips in groups** are neutral grey boxes here, amber on Bench, and pills on Codes. One `.dtc` component everywhere (mono, `--fs-sm`, state colour, no wrap).

**J6 — Test row layout.** Columns: empty square checkbox (no label) | title + underlined bulletin ref | `+` link | "Record result" button | flag button. The `+` (media attach) is underlined so it reads as **"±"**; its hit area is **12×23 px**. "Record result" wraps to two lines in some rows and not others (variable width).
*Fix:* `grid-template-columns: var(--tap) minmax(0,1fr) auto;` put attach + flag inside an overflow "⋯" menu or as 44 px icon buttons with SVG icons and `aria-label`; fixed-width "Record" button (`min-width:7.5rem; white-space:nowrap`).

**J7 — Completed/FAIL row state.** A FAIL result renders the title **struck through** with a green ✓ and "done 2026-10-14T07:58:26" wrapped over 3 lines; the FAIL value chip (`Fail · 404ms`) is also struck through.
*Fix:* no strike-through; left status rail coloured by result (`--sev-returned` fail, `--ok` pass, `--sev-chronic` inconclusive); result chip after title; time as `|when` on one line (`white-space:nowrap`).

**J8 — Bulletin refs** (`S2125000002`, `18-048-23`) are underlined links at 13 px inline after the title; on wrap they break at hyphens (`18-048-` / `23`). Add `.ref{white-space:nowrap; font-family:var(--mono); font-size:var(--fs-xs)}`.

**J9 — Long test titles with embedded sourcing.** Rows in the ADAS/Body/Network groups put the full rationale + citation inline in the title ("Read HALF directly on CAN-CH (grey A6): Fit the grey A6 adapter cable … GIORGIO_MODULE_MAP.md Table A (…) and GIORGIO_PLATFORM.md section 2."). Split into title (≤ 60 chars) / description (`--fs-sm --ink-2`) / source (`--fs-xs` mono, collapsed behind "Source").

**J10 — Progress pills** (`0/6`, `0/3`) float alone, left-aligned, after the "Add what you found" disclosure — not attached to their group heading. Move into the group header row right-aligned.

**J11 — Disclosure glyphs** mix `▶` 17 px, `▸` 10 px, `▼`, and "▶ + Evidence for ▶ + Evidence against" puts two triangles and two plus signs on one line. Use one CSS-drawn chevron on `summary::before`, rotate on `[open]`; hide default marker (`summary::-webkit-details-marker{display:none}`; `list-style:none`).

**J12 — Step nav (sticky bottom)**: "← Back" and "Next: Hypotheses →" have different widths and the primary fails contrast (G5); the FAB overlaps it (G8). Make it `grid-template-columns:auto 1fr`, 48 px tall, with safe-area padding `padding-bottom:max(12px, env(safe-area-inset-bottom))`.

### Record-result dialog
**D1** Title "Record a result" is a `<p>` at 17 px — make it `<h2 id>` and `aria-labelledby`.
**D2** **All** labels are uppercase with 1.26 px tracking, including the radio options ("PASS — NO FAULT FOUND"). Keep caps only for field labels; options in sentence case at `--fs-md`.
**D3** `input[type=number]` renders in Arial 13.33 px, **21 px tall, unstyled grey**, next to a styled 34 px "unit" input. Style all inputs the same: `min-height:var(--tap); padding:0 var(--space-3); border:1px solid var(--rule); background:var(--surface-2); border-radius:var(--radius-sm); font-size:var(--fs-md)` (16 px also stops iOS zoom; currently 13.33–14 px).
**D4** Radios are native 24 px Arial controls; use `accent-color:var(--accent)` and make the whole label the 44 px target.
**D5** "REASON (REQUIRED)" — show required with an asterisk + `aria-required`, error text under the field on submit; reason should be a `textarea` (2–3 rows) — currently a single-line input truncating long reasons.
**D6** Hypothesis `<select>` with an empty list still shows a highlighted dropdown; when there are no hypotheses, render "No hypotheses yet — add one in step 7" text instead.
**D7** Dialog `border-radius:12px` vs 3 px everywhere else (see §6 radii).

### Step 7 Hypotheses
**H1** Evidence items are **full sentences in bold monospace, green on green** ("P0455-00 freeze frame: above 85 %: EVAP monitor could not run ×"). Render as list items in sans `--fs-sm`, with the DTC token alone in mono, and a small "for/against" icon; `×` remove as a 44 px icon button with label.
**H2** Status buttons (`open | supported | refuted | confirmed`) — disabled "confirmed" is near-invisible (≈2:1). Use a segmented control; disabled state ≥3:1 plus `aria-disabled` + tooltip explaining why.
**H3** Guidance paragraph in amber 15 px ("Mark supported first. 5 piece(s)…") — amber text on black for a full paragraph is tiring; use an info callout (neutral text, amber left rule).
**H4** Suggested-hypothesis cards: first card has a **2 px white dashed border**, later cards grey dashed, and their content is dimmed. Use one "suggested" style: 1 px dashed `--rule`, `--surface` bg, full-contrast text, "Suggested" caps tag.
**H5** Empty grey progress bar under the hypothesis title has no label — add `aria-label` and a visible "0 of N tests" or remove.

### Steps 8–12
**S1** Step 8 tool cards: long paragraphs, sourced prices, confidence tags (`CORROBORATED`, `SINGLE-SOURCE`, `UNKNOWN`) inline in caps — use the `.status` component and collapse sourcing behind "Sources".
**S2** Step 12 "Tools used review": YES / NO / UNSURE caps toggles repeated for unnamed blank rows (three anonymous YES/NO/UNSURE rows appear with no tool name) — render empty "Other tool" rows only on demand ("+ Add another tool").
**S3** All-caps form labels ("MISSING TOOLS (COMMA SEPARATED)", "SKIP TOOLS REVIEW -- REASON (REQUIRED IF NOT SAVED ABOVE)") — sentence case, hint text under the field in `--fs-xs`.

---

## 5. Other pages

### Codes (`/codes`)
**C1** DTC codes **break at the hyphen** ("B1040-" / "64"). `td.code{white-space:nowrap}`.
**C2** Table is 807 px wide in a 485 px viewport with `table-layout:auto`; the Module column wraps to 8 lines ("Engine / ECM, Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)") and "4 mo / ago" wraps.
*Fix (≤ 640 px):* convert rows to cards (`display:grid` per `tr` with `td::before{content:attr(data-label)}`), or keep the table inside `.table-wrap{overflow-x:auto}` with `min-width` per column and shorten Module to the module acronym with the full name in `title`/second line.
**C3** Five text sizes in one table: 11.5 / 12 / 12.5 / 13.5 / 14 px. Use `--fs-sm` for cells, `--fs-xs` caps for headers.
**C4** Numeric column alignment mixed (count right, dates left, distance right, all mono). Right-align all numerics, `tabular-nums`, dates left in sans.
**C5** State pills: `chronic` amber all identical, `seen-once` / `recurring` at **4.12:1** (fail AA at 12 px). Bump `--sev-once` text or size to `--fs-sm` semibold.
**C6** Filter chips: "All", "Recommended" Title case; categories lowercase ("EVAP" vs "engine other"). Pick Title case and the same labels as the System column.
**C7** "29 of 29 codes over 39 logs" in mono + a green "real logs only" pill — sans, neutral.

### Code detail (`/code/P0455`)
**CD1** Freeze-frame data is a long list of label/value lines; use a 2-column `dl` grid with right-aligned `tabular-nums` values and units in `--ink-3`; let the two freeze frames sit side-by-side ≥ 720 px for comparison.
**CD2** "Expected ✓ / Not expected —" symptom list: replace glyph-as-meaning with icons + text and consistent alignment.

### Tests (`/tests`)
**T1** Every test card has a 3 px **red left border** (accent used as decoration → reads as "error"). Use `--rule` by default, state colour only when there is a result.
**T2** PASS / FAIL / Inconclusive / Not possible are `<button>`s in **Arial** (R3), mixed case ("PASS", "FAIL" caps; "Inconclusive", "Not possible" not), and "Not possible" wraps to its own row. Make a 4-segment control, sentence case, equal widths.
**T3** Inline result form: VALUE input full width, "unit" drops below it, HYPOTHESIS select floats right, SUPPORTS `for` select and REASON on a third row — misaligned grid. Use a 2-col grid: Value | Unit, Hypothesis (span 2), Supports | Reason.
**T4** "Recommended: open code P0440; …" is green text → green means pass elsewhere. Use `--ink-2` with a "Recommended" status chip.
**T5** Category/condition tags (`EMISSIONS`, `KOEO`) mono caps boxed, duration ("20 min") plain — unify as `.status` neutral chips.
**T6** Developer-only text visible ("CUORE today: no -- MCP-only via obd2.run_actuator with the ACTUATE ECM consent phrase…"). Hide behind `{% if profile == 'dev' %}`.

### Systems (`/systems`)
**SY1** SVG graph is a fixed 646×254 viewBox rendered at 646 px wide inside a scroller with "← scroll for more systems →" hint text. Make it responsive (`width:100%; height:auto`) and lay out vertically below 600 px.
**SY2** Node label "EVAP (evaporative emissions)" is **154 px in a 134 px node** — overflows the box; "Network / CAN buses" touches the edge; count badges overlap the node border. Measure text (`getComputedTextLength`) and size nodes to fit, or wrap labels with `<tspan>` and use short labels ("EVAP").
**SY3** SVG text uses `system-ui … sans-serif, sans-serif` at a fixed 12 px — fine family, but set `font-size` in CSS so it follows the scale; add `font-variant-numeric:tabular-nums` to badges.
**SY4** Edge-style legend uses text characters ("—— ----- ·······") — draw the three line styles as tiny inline SVGs matching the graph strokes.
**SY5** "Edge detail" disclosure rows: bold system names + plain "depends on" + tiny mono confidence word (`confirmed`, `unknown`) on its own wrapped line. Use the `.status` chip for confidence, keep it on the same line (`flex-wrap` with `gap`).
**SY6** Large "LIVE CHANNELS" paragraphs: known-good bands written as prose. Present as a table: Channel | Normal band | Condition | Confidence.

### Full scan (`/scan`)
**FS1** H1 "Full scan" 40 px/300 — light weight, much larger than other pages' titles. Use `--fs-3xl` semibold.
**FS2** Module table: module names mono, status as mono lowercase pills (`confirmed`, `unverified`, `unknown`); "unknown" has no pill (plain grey text) → misaligned column. Give every state a pill, sans `--fs-xs`.
**FS3** Two columns at 485 px squeeze the third group (Grey A6) under; FAB covers the ABS row's status. Single column below 560 px.

### Liveboard (`/liveboard`)
**L1** Different visual system (own `liveboard.css`): buttons 650–700 weight at 15–17 px, three equal-weight big buttons ("Start" accent, "Snapshot", "Demo") — Demo should be tertiary. No vehicle tab nav on this page (user loses the nav).
**L2** Identifiers in UI: `can_c / can_ihs / can_ch`, "needs blue_a5 / grey_a6", "BUS CAPTURE (can_ihs)". Map to human labels ("CAN-C", "Blue A5 cable").
**L3** "UNKNOWN DID" / "KNOWN" caps bold labels with no fixed width → the signal names don't line up. `grid-template-columns: 9ch 1fr`.
**L4** Empty values render as a heavy bar "▬" with tiny units ("bar, °C") at different baselines; channel names inconsistent case/duplicates ("engine rpm" and "Engine RPM", "vehicle speed" and "Vehicle speed"). Use an em dash in `--ink-3`, align value+unit on baseline (`display:flex; align-items:baseline; gap:4px`), dedupe/normalise names server-side.
**L5** Section headers ("SPEED & RPM", "PRESSURE & BOOST", "FREEZE FRAME") caps 16 px/650 — use `.caps` at `--fs-xs` with `--ink-3`, it's a group label.

### Report (`/report`)
**RP1** Hero overlaps header (R4/R5). Also on print — check `print.css` hides `.vhero` or lays it out in flow.
**RP2** Checklist items rendered with ASCII "[ ]" and **bold monospace citations** inline ("mes.knowledge Bulletin S1808000005 (BCM power-feed/fuse F82 cascade into U-codes)"). For screen and PDF: real checkbox glyph (☐ via CSS or SVG), citation as `--fs-xs --ink-3` sans footnote with only the ID in mono.
**RP3** "DOWNLOAD PDF" / "DOWNLOAD PDF (A4)" caps pill buttons — sentence case; label the difference ("Letter" vs "A4").
**RP4** Electrical-path blocks are repeated in full for each code (≈88 k characters on screen). Typography can't fix that; dedupe and reference ("Same path as P0440").
**RP5** H3s at 19 px here vs 15 px on the Job page for the same group titles — follows from the scale in §1.

---

## 6. Component & token consistency

| Item | Found | Standardise to |
|---|---|---|
| Border radius | 0 (details/sections), 3 px (buttons, chips), 12 px (dialog, some buttons), 50 % (FAB), full pills (filter chips, system pills on Codes, progress pills) | `--radius-sm 4px` inputs/chips-square, `--radius 8px` cards/dialogs/buttons, `--radius-pill` status pills |
| Font weights | 300, 400, 500, 600, 650, 700 | 400 / 500 / 600 / 700 |
| Caps tracking | 0.24, 0.78, 0.84, 0.98, 1.08, 1.125, 1.2, 1.26 px | `--tracking-caps: 0.06em` |
| Chips | ≥6 visual variants (code, status, sys link, tool pill, legend, filter) | 3 components: `.dtc`, `.status`, `.tag` (+ `.filter-chip`) |
| Mono usage | sentences, citations, tool lists, timestamps, footer | IDs, codes, P/Ns, values+units, keys only |
| Accent red | primary buttons, step-current, H2 rules, test-card rails, FAIL | primary actions + returned/fail state only |
| Tap targets < 32 px | `a.sysb-chip` 23 px, `a.media-attach-add` 12×23, `a.step-ref` 16 px, summaries 19–21 px, footer links 13 px | ≥ 44 px hit area (padding or `::after` inset) |
| Input font sizes | 13.33 (number/checkbox), 14 (text/select/textarea) | 16 px |

---

## 7. Implementation order & acceptance checks

1. **Foundation** (§1): token block, scale, `font:inherit` on controls, delete duplicate `:root`/`body` rules. *Accept:* `grep -E "font-size:\s*[0-9.]+px" static/*.css` returns only lines inside `:root`.
2. **Layout bugs** R4–R7, G4, G8, J1. *Accept:* `document.documentElement.scrollWidth === innerWidth` on every route at 360, 485, 768, 1280 px; full vehicle name visible on Bench; nothing paints over `header` on Report.
3. **Contrast** G5, C5, H2, light `--ink-3`. *Accept:* zero text nodes < 4.5:1 (or < 3:1 for ≥ 18.66 px / ≥ 14 px bold) in both themes.
4. **Components**: `.dtc`, `.status`, `.tag`, test row grid, dialog form, disclosure chevron.
5. **Copy hygiene**: `|dash`, `pluralize`, `|when`, de-identifier labels (`live_board`, `can_ihs`, `blue_a5`), hide dev text.
6. **Page-specific** items in §3–§5.

Paste this in DevTools on each route (both themes, each width) — it is the same script used for this audit:

```js
(()=>{const L=c=>{const m=c.match(/[\d.]+/g);if(!m)return 0;const[r,g,b]=m.slice(0,3).map(v=>{v/=255;return v<=.03928?v/12.92:((v+.055)/1.055)**2.4});return .2126*r+.7152*g+.0722*b};
const bg=e=>{for(;e;e=e.parentElement){const c=getComputedStyle(e).backgroundColor,a=c.match(/[\d.]+/g);if(a&&(a.length<4||+a[3]>.5))return c}return getComputedStyle(document.body).backgroundColor};
const out={overflowPx:document.documentElement.scrollWidth-innerWidth,sizes:new Set,arial:0,contrast:[],small:[],tap:[]};
for(const e of document.querySelectorAll('body *')){const s=getComputedStyle(e);if(s.display=='none')continue;const r=e.getBoundingClientRect();
 if([...e.childNodes].some(n=>n.nodeType==3&&n.textContent.trim())){out.sizes.add(s.fontSize);if(s.fontFamily.startsWith('Arial'))out.arial++;
  const fs=parseFloat(s.fontSize);if(fs<12)out.small.push(e);const a=L(s.color),b=L(bg(e)),cr=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
  if(cr<((fs>=18.66||(fs>=14&&+s.fontWeight>=700))?3:4.5))out.contrast.push([cr.toFixed(2),e])}
 if(e.matches('a,button,summary,input:not([type=hidden]),select')&&r.width&&r.height<44)out.tap.push(e)}
out.sizes=[...out.sizes];console.log(out);return out})()
```
Targets: `overflowPx 0`, `sizes.length ≤ 7`, `arial 0`, `contrast []`, `small []`, `tap []` (allow inline text links inside paragraphs).

---

### Not covered / to re-check
Desktop layouts (≥ 1024 px) and print/PDF output were not rendered in this pass; the RTL and 200 % zoom cases weren't tested. Items marked with measured values (contrast ratios, widths, counts) were read from computed styles; visual judgments (hierarchy, alignment, legibility) are from screenshots at 485 px.
