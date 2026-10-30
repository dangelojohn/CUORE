# PARTS area: audit and task sheet

Date: 2026-10-30. Read-only audit. Reference car: 2018 Stelvio 2.0T (949), VIN ZASFAKPN5J7B88115.

## Answer first

The parts area is a good picture book, not yet a parts desk. It holds 1,821 Mopar part rows on 304 diagrams (128 diagrams have parts), 66 torque values, and 11,196 shop listings (10,822 of them Autodoc UK aftermarket). But it has no supersession, no quantity, no price on any Mopar row, no VIN or model-year range, no callout positions, no labour time. Only 24 curated cards link parts to codes and jobs, and 16 of their 24 OEM numbers are marked UNKNOWN. The data is one crawl from 2026-10-24 (shop prices 2026-10-27). **Top 3 tasks:** (1) pull the TechAuthority parts, specifications and removal/installation sections for this car and use them to verify the part numbers and fill torque, tools and one-time-use items; (2) re-verify or retire the 24 curated cards so every code-to-part link rests on a sourced number; (3) add VIN-filtered fitment, supersession and stock/price (via AlfaCore/Odoo) so a technician gets "which part, which number, can I get it, what else to replace".

## Current state

### Pages and routes
- `/catalog` (search, group tiles), `/catalog/g/{gid}`, `/catalog/d/{did}` (diagram + parts), `/catalog/p/{pn}` (one part), `/catalog/other` and `/catalog/other/autodoc/{slug}` (aftermarket), `/catalog/w/{wid}` (Wrangler 2.0 GME engine diagrams, 44), `/catalog/api/typeahead`, image routes. File: `cuore/web/catalog_routes.py`.
- `/v/{vin}/parts` (curated job parts). File: `cuore/web/parts_routes.py`. Templates: `catalog_*.html`, `_catalog_*.html`, `parts.html`, `_part_card.html`, `_standard_parts.html`.
- API: `/api/parts`, `/api/parts/for-code/{code}`, `/api/parts/for-job/{job}` (CUORE_SIDE_CONTRACTS.md).
- Services: `cuore/services/parts_catalog.py` (626 lines), `parts_bridge.py` (409), `standard_parts.py` (242); `mes-log-mcp/mes/parts.py` (24 curated parts). Data file `cuore/data/parts_catalog_groups.json` (in git, 6 keys). Tests: `check_parts_catalog.py`, `check_parts_page.py`.

### Data in C:\ProgramData\cuore\parts_catalog (not in git)
| File | Size | Modified | Content |
|---|---|---|---|
| stelvio-2018-2.0l/catalog.json | 13.5 MB | 2026-10-26 (built 2026-10-27) | the built catalogue |
| stelvio-2018-2.0l/img/ | webp images | 2026-10-24 | diagram and part photos |
| sources/stelvio-2018-2.0l-catalogue.json | 754 KB | 2026-10-24 | Mopar Online Parts crawl, fetched 2026-10-24T16:41Z |
| sources/stelvio-autodoc-aftermarket.json | 6.3 MB | 2026-10-26 | Autodoc UK |
| sources/stelvio-centerline-products.json | 121 KB | 2026-10-24 | centerlinealfa.com |
| sources/stelvio-canada-aftermarket.json | 14 KB | 2026-10-24 | moparcanadaparts.com |
| sources/wrangler-2019-gme-2.0l-engine.json + wrangler-gme/img | 300 KB | 2026-10-26 | Jeep GME engine (shared-engine reference) |
| standard_parts.json + sources/standard/ | 0.8 KB + 3.6 KB | 2026-10-26 | owner-attested standards (oil filter Hengst H98W) |
| design/BRIEF_*.md | 5-7 KB | 2026-10-24 | design briefs |

Catalogue contents: 13 groups, 128 sections, 304 diagrams, 1,821 part rows, 11,196 listings, 66 torque values over 34 sections, 44 Wrangler diagrams. 4 sections are excluded as not this car (2.9L V6, 8HP75).

### Record schema
- Part row: `ref, pn, name, description, notes, info, fitment, url, photos`.
- Diagram: `id, slug, index, group, section, title, image, source_url, parts`.
- Listing: `source, brand, pn, sku, name, notes, price, currency, msrp, url, category, fitment, fitment_why, price_date, ean, specs, interchange`.
- Curated card (24): `key, name, what_it_does, oem[number, confidence, source], supersedes, aftermarket, fits, location, related_codes, related_jobs, torque_keys, price, buy, images, notes`.

### Links today
- Catalogue part page links to: its diagram and group, curated card, torque rows (matched by name words, labelled as a name match), CUORE records (jobs, notes, symptoms, observations, shop visits) and the TSB catalogue (168 items) when they mention the part number.
- Curated cards link to codes (7 of 24 have related codes; 18 codes in all, mostly EVAP, misfire, boost, P1CEA) and jobs (24 of 24).
- No link to systems, sensors or fuses views, no procedure link, no recall link. Odoo link is design only: `alfa_parts.part` (part_number, category, fits, alternatives graded safe/interim/not_recommended, kits with `estimated_labor_hours`) exists in AlfaCore; CUORE exports no parts in the bundle (grep of `bundle_export.py` finds none).

## Data quality (catalog.json, measured)
| Field | Filled | Of 1,821 |
|---|---|---|
| part number, name, ref, url | 1,821 | 100% |
| notes (engine and transmission text only) | 1,520 | 83.5% |
| fitment flag (`own` 1,516, `other-engine` 2, blank 303) | 1,518 | 83.4% |
| description | 949 | 52.1% |
| photo | 1,202 | 66.0% |
| info (extra detail) | 19 | 1.0% |
| supersession | 0 | 0% |
| price (Mopar rows) | 0 | 0% (not required: owner decision 2026-10-30) |
| quantity per vehicle | 0 | 0% |
| VIN range / model year | 0 | 0% |
| callout positions (`marks`) | 0 of 304 diagrams | 0% |

- Diagrams with no part rows: 176 of 304 (58%). Check whether these are blank pages or missed pages.
- Duplicates: 1,625 unique part numbers; 160 numbers appear more than once (356 rows). Normal across diagrams, but the page should show each once with "also on diagram X".
- Staleness: Mopar crawl 2026-10-24 (6 days old); listings priced 2026-10-26/27. 204 listings have no price date. 11,039 of 11,196 listings have fitment "unverified" (only 20 "own", 109 "by-name"). Only 12 listing part numbers match a Mopar diagram number: the aftermarket data is nearly unlinked to the OEM numbers.
- Curated cards: 23 of 24 have no price; OEM confidence is UNKNOWN on 16, SINGLE-SOURCE 4, CORROBORATED 4, CONFIRMED 1. The 6 fixture entries in `parts_bridge.py` carry RockAuto-style prices dated 2026-09-20 and forum-sourced numbers (for example esim 68245527AA). Treat as unverified until checked against a catalogue or TechAuthority.
- Parts linked to a code or system: at most the 24 curated cards (7 with codes). Number of catalogue rows that match a curated card: not measured. Catalogue parts linked to systems, sensors or fuses: 0.
- Coverage: Stelvio 2.0T only. No Giulia catalogue; the 2.9L and 8HP75 sections are excluded, not stored.

## Requirements for a FULL parts area
Technician question: which part, which number, can I get it, how long to fit, what else to replace.
1. VIN-filtered fitment (build date, engine, transmission, market) and a clear "does not fit" flag.
2. Supersession chains, old number to current number, with date.
3. Diagram with callouts the technician can tap.
4. Part location on the car, linked to the systems, sensors and fuses views.
5. Removal and installation procedure, torque, special tools, one-time-use items (gaskets, bolts, seals) attached to the part.
6. Fluids and capacities, with spec.
7. Kits and "replace together" lists.
8. Bulletins and recalls that change a part or a procedure, shown on the part.
9. Warranty and part-return rules (to confirm on TechAuthority).
10. Links from every code, lead, hypothesis and job to the part, with the reason.
11. Stock from Odoo via AlfaCore, with date and supplier. Mopar prices are not required (owner decision 2026-10-30).
12. Labour time, only from an authoritative source, with source and date.
13. Other models: Giulia first (same platform), then others, with marque data in config.
14. Source and date on every fact; vendor data stays in ProgramData.

## Gap table
| Requirement | Today | What upgrades it | Source | Priority |
|---|---|---|---|---|
| Verified part numbers | 1,821 rows from one crawl; curated 16 of 24 UNKNOWN | Cross-check against TechAuthority parts lists and recall/bulletin part numbers | TechAuthority parts info (to confirm on TechAuthority) | P1 |
| VIN-filtered fitment | 0% VIN/year; 83% engine text only; 303 blank | Fitment notes per part, VIN or build-date ranges, filter by VIN | TechAuthority parts / build data (to confirm); Mopar catalogue refresh | P1 |
| Supersession | 0 of 1,821 | Chain old to new number | Mopar catalogue refresh; TechAuthority (to confirm) | P1 |
| Quantity per vehicle | 0 | Qty column | Mopar catalogue refresh | P2 |
| Callouts on diagrams | 0 of 304 diagrams (44 Wrangler diagrams have marks) | Capture callout coordinates; build tap targets | Mopar catalogue refresh; CUORE build | P2 |
| Empty diagrams | 176 of 304 | Re-crawl and check; mark honestly if the source has none | Mopar catalogue refresh | P1 |
| Removal and installation | None attached to parts | Link procedure per part | TechAuthority service manual R&I sections | P1 |
| Torque, tools, one-time-use | 66 torque values on 34 of 128 sections; 33 rows mention kit/single/replace in text | Fill from service manual specs; add tool and one-time-use fields | TechAuthority specifications and procedures | P1 |
| Fluids and capacities | Oil filter standard only | Fluid table with spec and capacity | TechAuthority specifications | P2 |
| Part location | None | Link to systems, sensors, fuses, electrical path | CUORE build; TechAuthority component locations (to confirm) | P2 |
| Bulletins/recalls on parts | TSB match by text only; 168 TSB items | Tie bulletin and recall part numbers to catalogue parts | TechAuthority bulletins and recalls | P1 |
| Code/lead/job to part | 24 curated cards, 7 with codes | Link by sourced diagnosis, with reason | CUORE build, using TechAuthority diagnostic information | P1 |
| Stock | none on Mopar rows | Odoo stock per part number via AlfaCore, dated (Mopar prices not required, owner 2026-10-30) | AlfaCore-Odoo | P1 |
| Labour time | None | Store only if an authoritative source publishes it | TechAuthority labour operations (to confirm on TechAuthority) | P3 |
| Warranty/part return | None | Rules text per part class | TechAuthority warranty section (to confirm on TechAuthority) | P3 |
| Kits | None | Kit membership | Mopar catalogue refresh; AlfaCore `part.kit` | P2 |
| Aftermarket match | 11,039 of 11,196 unverified; 12 pns match OEM | Match by interchange or EAN, label as aftermarket | Aftermarket re-crawl; CUORE build | P3 |
| Giulia and others | None | Second catalogue, same schema | Mopar catalogue (Giulia); TechAuthority | P2 |
| Europe numbers | None | EU part numbers and differences | stellantisiop.com (owner access) | P3 |

## Pull list from TechAuthority
Scope: 2018 Stelvio 2.0T first. Note "not offered" for anything not found. Save raw material to C:\ProgramData\cuore\research\techauthority_parts_<date>\ with SOURCES_AND_FINDINGS.md.

**Parts and illustrations (to confirm on TechAuthority)**
- [ ] Parts lists with illustrations for 2.0T, 8HP50, Q4. CUORE: compare to the 1,821 rows and flag mismatches. Closes: verified numbers, empty diagrams.
- [ ] Supersession or interchange notes. CUORE: build the chain. Closes: supersession.
- [ ] Kit and service-kit contents. CUORE: kit table. Closes: kits.

**Service manual: removal and installation**
- [ ] R&I procedure for each catalogue section (start with the ones behind the 24 curated cards: EVAP, ignition, boost, brakes, filters). CUORE: attach to the part page. Closes: procedures.
- [ ] Special tool lists and tool numbers. CUORE: tool field per part; feed tool inventory. Closes: tools.
- [ ] One-time-use items called out in procedures (bolts, gaskets, seals, clips). CUORE: a "replace with it" list. Closes: one-time-use.

**Specifications**
- [ ] Torque tables for every section. CUORE: fill the 94 sections of 128 with no torque; replace name-matched rows. Closes: torque.
- [ ] Fluids, capacities and specifications (oil, coolant, ATF, brake, A/C refrigerant and oil, washer). CUORE: fluid table. Closes: fluids.
- [ ] Filter, belt, spark plug, brake pad and bulb specs. CUORE: confirm the standards file. Closes: verified numbers.

**Component locations and wiring**
- [ ] Component location views. CUORE: link part page to systems, sensors, fuses views. Closes: location.
- [ ] Wiring diagrams and connector views. CUORE: electrical path for each electrical part. Closes: location.

**Bulletins, recalls, campaigns**
- [ ] Technical service bulletins and recalls with part numbers. CUORE: show on the part and the code. Closes: bulletin links.
- [ ] Campaign notices with part numbers. Same use.

**Diagnostics**
- [ ] Diagnostic procedures per DTC, with the parts they name. CUORE: sourced code-to-part links. Closes: code/lead/job links.

**Warranty and labour (to confirm on TechAuthority)**
- [ ] Warranty coverage terms and part-return rules. Closes: warranty.
- [ ] Labour operation list and times, only if published. Closes: labour time.

**Other models and Europe**
- [ ] Giulia 2.0T equivalents of all items above. Closes: other models.
- [ ] stellantisiop.com: EU part numbers, differences by market. Closes: Europe.

## Data to refresh or fix
- [ ] Re-crawl Mopar Online Parts for the Stelvio, record new `fetched_at`, diff against 2026-10-24 (1,821 rows).
- [ ] Investigate the 176 diagrams with no part rows (of 304).
- [ ] Fill or flag blank fitment on 303 rows and blank description on 872 rows.
- [ ] Add stock for the 1,821 Mopar rows through AlfaCore, not by scraping. (Mopar prices: not required, owner 2026-10-30.)
- [ ] Re-verify the 24 curated cards; 16 have UNKNOWN OEM confidence. Retire or source each.
- [ ] Remove or re-source the fixture prices (2026-09-20) on the 6 fixture cards.
- [ ] Set price date on 204 listings that have none; refresh the 2026-10-27 Autodoc prices.
- [ ] Re-check 11,039 "unverified" listings; match to OEM by interchange or EAN only.
- [ ] Group the 160 repeated part numbers (356 rows) as one part on several diagrams.
- [ ] Add callout `marks` to 304 diagrams.
- [ ] Review the 4 excluded sections (2.9L, 8HP75) in case the owner wants Quadrifoglio later.

## CUORE builds
- [ ] Part page "answer card" at top: part, number, fits this VIN, stock (dated), torque, tools, one-time items, "replace with it". Gaps: fitment, stock, torque.
- [ ] VIN filter using build data read in a CUORE session (no raw adapter scripts).
- [ ] Schema fields: supersedes, qty, vin_range, one_time_use, tool_ids, kit_id, source, fetched_at.
- [ ] Link parts to systems, sensors, fuses, electrical path, "open in layout".
- [ ] Code-to-part and job-to-part links with a written reason and a source; cover more than the 18 codes now linked.
- [ ] Tie TSB and recall entries to part numbers (replace text-only matching).
- [ ] Export parts to the AlfaCore bundle (`alfa_parts.part`, alternatives with grade, kits) and read stock back.
- [ ] Extend `check_parts_catalog.py` to report the fill rates above on every build.
- [ ] Second catalogue loader for Giulia, marque data in config.
- [ ] Show source and date on every number on every page.

## Owner decisions needed
1. May TechAuthority content be stored in ProgramData for CUORE to display (licence), and is it internal use only?
2. Which sections first: EVAP, misfire/ignition, boost, brakes, service items (matches open Stelvio work)?
3. Re-crawl Mopar Online Parts, or make TechAuthority the main parts source and keep the crawl as backup?
4. Stock: Odoo only, or also supplier lookups? Which supplier? (Mopar prices: decided not required, 2026-10-30.)
5. Labour times: wanted if only a dealer source offers them?
6. Giulia next, or stay on the Stelvio until it is complete?
7. Keep or drop the 11,196 aftermarket listings (mostly Autodoc UK) in the main view?

## Sources
- C:\ProgramData\cuore\parts_catalog\stelvio-2018-2.0l\catalog.json (measured 2026-10-30).
- C:\Users\User\mcp-servers\cuore\services\parts_catalog.py, parts_bridge.py, standard_parts.py; cuore\web\catalog_routes.py, parts_routes.py; mes-log-mcp\mes\parts.py; cuore\data\tsb_catalogue.json, parts_catalog_groups.json.
- docs\integration\ALFACORE_MODEL_MAP.md (alfa_parts), CUORE_SIDE_CONTRACTS.md (parts API).
- Not browsed: TechAuthority, stellantisiop.com. Items marked "to confirm on TechAuthority" are unverified.
