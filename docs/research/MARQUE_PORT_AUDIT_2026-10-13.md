# Marque port audit -- 2026-10-13

Roadmap item 9: CUORE is Alfa-branded first and must port to Maserati
(Levante, Grecale) and Ferrari (Purosangue), with marque specifics kept in
data/config, not hardcoded in templates/services.

## Method

One grep over `cuore/web/templates`, `cuore/web/static/*.css`,
`cuore/services`, `cuore/live` for: `Stelvio`, `Giulia`, `Alfa`, `alfa`,
`Giorgio`, `GME`, `2.0T`, `MultiAir`, `ZASFAKPN5J7B88115`, and marque
colours. Three hits (`dossier_bridge.py:524`, `jobs_bridge.py:272,276`)
are substring false positives (`GME` matching inside "frag**me**nt" /
"aug**me**nt") and are not listed below.

Classification:
- **(a) data** -- should come from `mes.platform`/the vehicle record
  (model name, engine, platform); fixed this pass.
- **(b) case sample** -- sourced Alfa-case copy (docs, seeds, reference
  material, real experience links); correct as-is, left alone.
- **(c) theme** -- keys off `data-marque` already; correct as-is.

## Findings

| File:line | Text | Class | Action |
|---|---|---|---|
| `cuore/web/routes.py` (`_page()`, new) | `marque` was **never** computed -- no Python file set it, so every page's `data-marque` silently defaulted to `"alfa"` regardless of vehicle | (a) | **Fixed.** Added `_marque_for(ctx)`, called from `_page()` for every `/v/{vin}/*` route (all of them already pass `vin=vin` into `_page()`'s ctx), backed by new `mes.platform.marque_for_vin()` + `mes_bridge.marque_for_vin()`. Falls back to `"alfa"` (this project's default marque) for no-vin pages and unrecognised WMIs, never leaking a raw `"unknown"` into `data-marque` where no theme matches it. |
| `cuore/web/templates/base.html:2,7` | `data-marque="{{ marque\|default('alfa') }}"` | (c) | Correct as written; was dead code until the fix above, since `marque` was never in context. No change needed here. |
| `cuore/web/templates/m_base.html:2` | same pattern | (c) | Correct; file excluded from this pass (`m_*.html`) regardless. |
| `cuore/web/templates/intake.html:7,24` | `{{ t('start_this_stelvio') }}` -> i18n.py's English text is literally "Start this Stelvio", shown on `/start` for every mechanic regardless of which car they're about to type in | (a) | **Fixed.** `i18n.py` is off-limits this pass, so the key is no longer called here: both occurrences now read the literal, marque-neutral "Start this car" (no VIN is known yet on this page, so there's nothing to theme off of either). |
| `cuore/web/templates/_flow_bar.html:21,50,77` | Job-complete CTA: `_lbl('tools_away_start_next', 'Tools away. Start the next Stelvio')`. `t` is always defined in the real app, so the fallback never fires -- the real text, from `i18n.py`, is Stelvio-specific and renders on the Job page's flow bar for any car | (a) | **Fixed.** Stopped routing this one string through `t()`/i18n.py; now a literal "Tools away. Start the next car" written directly in the template. Doc comments (lines 21, 50) updated to match; `cuore/tests/check_flow_bar.py`'s matching assertions updated too. |
| `cuore/web/templates/modules.html:104` | "On Giulia and Stelvio only **Bus A** ... is reachable" | (a)/(b) borderline | **Partially fixed.** `/modules` is a static reference page (no VIN, no marque context) documenting the Giorgio-platform bus map (sourced from `GIORGIO_MODULE_MAP.md`), same category as `cuore/live/*.py`. Added "and Grecale" -- sourced fact: `mes.platform.PLATFORMS["stelvio"]["shared_with"]` already records Grecale as a CORROBORATED Giorgio-platform-mate. Left Levante/Purosangue unaddressed: their bus topology has never been researched (`mes.platform` records it `UNKNOWN`), so there is no sourced data to port in. |
| `cuore/web/templates/modules.html:7-12,39,66,76,89` | "Giorgio bus" column header/copy, `m.on_giorgio` field | (b) | Left as-is. This is the underlying data model's own field name for a static, VIN-less reference table of the Giorgio platform's module map -- not per-vehicle UI chrome. Extending it to Levante's/Purosangue's different architectures needs new research, out of scope here. |
| `cuore/web/templates/_vbar.html:28-29` | `_taglines = {"alfa": "..."}`; maserati/ferrari get no tagline (`None`, rendered as nothing) | (c) | Correct, graceful degradation -- `{% if _tagline %}` already guards it. No Alfa text leaks for another marque; just no tagline shown yet. Not a defect; a future nice-to-have (add maserati/ferrari taglines) is out of this audit's scope. |
| `cuore/live/addressing.py`, `buses.py`, `coverage.py`, `did_catalog.py`, `layouts.py`, `obd.py`, `ops.py`, `readall.py`, `safety.py`, `stream.py`, `audit.py` -- every Giorgio/Stelvio/Giulia reference | (b) | Left as-is. This is the sourced, documented live-link knowledge base for the one platform this project has actually reverse-engineered (Giorgio). `layouts.py`'s `_stelvio_*()` function names and `"stelvio_*"` layout **ids** are internal identifiers never shown to a user -- the layout **titles** they return ("Engine basics", "Boost / turbo", "EVAP job", "Transmission", "TPMS") are already marque-neutral. |
| `cuore/services/parts_bridge.py:86-215` | Parts catalogue `"fits": "Alfa Romeo Giulia/Stelvio 2.0T (2017-2022)"` etc., with real sourced links (stelvioforum.com, alfaowner.com) | (b) | Left as-is. Sourced parts data for the one car this corpus actually has; inventing Maserati/Ferrari part numbers would violate the "never invented" experience-links rule. |
| `cuore/services/shop_bridge.py:41-43` | `_WMI_MAKES = {"ZASF": "Alfa Romeo", "ZN6": "Maserati", "ZN7": "Maserati"}` | (b)/already-correct | Already marque-aware (make only, model deliberately "UNKNOWN" rather than guessed). No change. |
| `cuore/services/mes_bridge.py:487` | "On this Stelvio the newest..." (docstring, explaining *why* a specific ordering rule exists) | (b) | Left as-is; explanatory comment about this project's real case, not UI copy. |
| `cuore/services/experience_bridge.py:103` | docstring example `(e.g. "giulia")` | (b) | Left as-is; a docstring example of a data value, not a hardcoded display string. |
| `mes-log-mcp/mes/systems.py`, `layout_systems.py`, `faulttree.py` -- "no GU/Stelvio-specific TSB citation found" / "not Stelvio-specific" / "Stelvio/Giulia-specific" idiom (~20 occurrences, incl. 2 split across adjacent string literals) | (a) | **Fixed.** This disclaimer idiom means "this is generic engineering fact, not unique to the Stelvio" -- but hardcoded the car name into a sentence meant to be car-agnostic. Mechanically replaced with "model-specific" throughout (meaning-preserving: the disclaimer's whole point was genericness). This was the one hit that actually reached a Maserati-VIN page in testing (`/v/{vin}/systems`). |
| `mes-log-mcp/mes/electrical.py`, `experience.py`, `known_good.py`, `maintenance_specs.py`, `mechanic_tests.py`, `service_specs.py` -- sourced reference data, real YouTube/forum links, maintenance/service specs explicitly for "2018 Alfa Romeo Stelvio 2.0T (US)" | (b) | Left as-is. Real, sourced, case-specific reference data (feedback_experience_links/feedback_search_past_sessions memory rules both require this to stay sourced, never invented). |
| `mes.known_good`'s reference bands (e.g. idle-RPM, cited from stelvioforum.com) | (b), flagged | **Not fixed, flagged.** `known_good_payload()`'s own docstring says it "Always includes every channel's reference band" -- by design, the same confidence-labelled band for every vehicle, regardless of marque. This is the one place the Maserati-VIN Systems-page check (below) had to be scoped narrower rather than asserting zero Stelvio/Alfa text on the whole page: the citation is sourced, correctly caveated ("not used here as it is a different engine... confirm against TechAuthority or this car's own MES-logged idle RPM"), and there is no sourced Maserati/Ferrari equivalent to substitute in. Marque-gating this whole knowledge base is a real follow-up, out of this pass's scope. |

## Fixes made

1. `mes-log-mcp/mes/platform.py` -- added `marque_for_vin(vin)`: WMI
   `ZAS`/`ZAR` -> `alfa`, `ZN6`/`ZAM` -> `maserati`, `ZFF` -> `ferrari`,
   else `"unknown"`.
2. `cuore/services/mes_bridge.py` -- thin passthrough `marque_for_vin(vin)`.
3. `cuore/web/routes.py` -- `_page()` now computes `marque` from
   `ctx["vin"]` (when present) via the above, falling back to `"alfa"` for
   no-vin pages and unrecognised WMIs. This is the root-cause fix: every
   `/v/{vin}/*` page's `data-marque` was hardcoded to `"alfa"` before this,
   because nothing ever set the variable `base.html`'s `marque|default
   ('alfa')` was reading.
4. `cuore/web/templates/intake.html` -- "Start this Stelvio" (x2) ->
   "Start this car".
5. `cuore/web/templates/_flow_bar.html` -- "Tools away. Start the next
   Stelvio" -> "Tools away. Start the next car"; doc comments updated.
6. `cuore/web/templates/modules.html` -- added sourced "and Grecale" to
   the Bus-A reachability note.
7. `mes-log-mcp/mes/systems.py`, `layout_systems.py`, `faulttree.py` --
   "Stelvio[/Giorgio|/Giulia][-specific]"/"GU/Stelvio-specific" disclaimer
   idiom -> "model-specific" (meaning-preserving).
8. `cuore/tests/check_flow_bar.py` -- updated its two Stelvio-text
   assertions to match fix #5.
9. `cuore/tests/check_marque_port.py` -- new TestClient-only (no Edge)
   check: Maserati fixture VIN `ZN661XUA9JX000001` (synthetic one-log
   fixture, isolated `MES_LOG_DIR`, no real corpus touched) gets
   `data-marque="maserati"`, a "Maserati" display name, and no
   "Stelvio"/"Alfa" text on Bench/Job/Tests (full-page) and Systems
   (title/chrome-scoped, per the known-good caveat above); `/start`
   itself reads "Start this car", not "...Stelvio".

## Verification run

- `check_marque_port.py`: **24/24 passed.**
- `check_screens.py`: **28/28 passed** (Edge was available on this
  machine, so its one Edge-dependent overflow check ran for real rather
  than being skipped).
- `check_theme.py`: **6/6 passed** (same -- Edge available, ran in full).
- Spot-checked for regressions from the `mes-log-mcp` text edits:
  `check_systems.py`, `check_layout_systems.py`, `check_electrical.py`,
  `check_maintenance.py`, `check_service.py`, `check_experience.py`,
  `check_known_good.py` (all under `mes-log-mcp/tests/`), plus
  `check_bench.py` and `check_flow_bar.py` (under `cuore/tests/`, against
  the real Stelvio VIN) -- all green, no regressions.

## Not fixed (explicitly out of scope)

- `mes.known_good`'s reference bands (see table above) -- would need a
  marque-gating layer plus sourced Maserati/Ferrari data that does not
  exist yet.
- `cuore/web/templates/modules.html`'s Levante/Purosangue bus topology --
  `UNKNOWN` in `mes.platform`, needs new research, not a wiring fix.
- `_vbar.html`'s per-marque taglines -- maserati/ferrari currently render
  no tagline (not wrong, just not filled in yet).
