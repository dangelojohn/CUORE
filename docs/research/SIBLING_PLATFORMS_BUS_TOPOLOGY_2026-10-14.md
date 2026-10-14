# Sibling Platforms: Grecale / Levante / Purosangue Bus Topology — 2026-10-14

**Purpose.** `mes.platform` has long marked the Maserati Levante's and Ferrari
Purosangue's OBD bus topology `UNKNOWN` (and Grecale's, at the pin/module
level, even though Grecale's *platform* relationship to this project's
Stelvio is already `CORROBORATED` — see `mes.platform.PLATFORMS`). This pass
researched all three — Grecale (Giorgio), Levante (M161, Ghibli/Quattroporte-
derived), Purosangue — against the same evidence bar the rest of this
project uses: a sourced fact gets `CONFIRMED`/`CORROBORATED`/`SINGLE-SOURCE`;
anything not found, or found only as an unverifiable AI-search summary with
no quotable primary page, stays `UNKNOWN`. Per the CUORE core directive
("diagnose on evidence"), nothing here is inferred from the Giorgio pinout
just because a car shares that platform.

**Method.** 12 web calls total (the budget for this pass): 4 `WebSearch`
sweeps, then 8 `WebFetch` pulls of the most promising specific pages. Sources
cited below carry the URL and the fetch/search date (2026-10-14 throughout).

---

## Headline / honest coverage statement

**Almost nothing at the pin/bitrate/module level survived verification.**
Every direct fetch of a page that looked like it would answer "which pins,
which bitrate, which modules" either didn't mention the car in question
(the FCA SGW bypass install doc names only Giulia/Stelvio 2018+, no
Maserati), 403'd, or redirected through a bot-paywall (`tollbit.*`) that
this pass could not get past within budget. The few facts that did land are
platform/chassis-code facts and vendor-support facts, not bus topology.
**Bus pins, bitrates, security-gateway presence/model-year, bypass-cable
applicability, and per-bus module+address lists are recorded `UNKNOWN` for
all three cars** except where a table cell below says otherwise. This is a
negative result worth keeping: it tells the next session not to assume the
Giorgio pinout transfers, and not to re-spend the search budget on queries
this pass already tried (listed per car below).

---

## Grecale (Giorgio platform, Maserati execution)

| Point | Finding | Confidence | Source |
|---|---|---|---|
| Platform relationship to Stelvio/Giulia | Shares the Giorgio platform (body structure, GME T4 2.0L engine family) | CORROBORATED | Already in `mes.platform.PLATFORMS["grecale"]`; unchanged this pass |
| OBD pins 6/14 (CAN-C), 3/11 (CAN-IHS), 12/13 (CAN-CH) | **Not found for Grecale specifically.** The Giorgio pinout is sourced for Stelvio/Giulia (`cuore/live/buses.py`, `docs/research/CONNECTIVITY_AND_SGW.md`) but no source names the Grecale's own OBD-port pin assignment. Not carried over. | UNKNOWN | — |
| Bitrates (500k CAN-C, 125k CAN-IHS, 500k CAN-CH) | Same reasoning — not sourced for Grecale | UNKNOWN | — |
| Security gateway present, and since what model year | A web-search summary claimed the Grecale (2021+) has a "built-in" SGW unlike the external SGW on Ghibli/Levante/Quattroporte — but this was the search tool's own synthesis, not a quoted line from a fetched page, and could not be traced to a primary source this pass. The one SGW install doc actually fetched names only Alfa Romeo Giulia/Stelvio, both "Manufactured 2018+" — no Maserati mention at all. | UNKNOWN | shopeurocompulsion.net SGW bypass install doc (fetched 2026-10-14) confirms 2018+ for Giulia/Stelvio only |
| Bypass cables (MES A5/A6 or other) | MultiEcuScan's own front page (fetched 2026-10-14) names its supported brands as "Fiat, Alfa Romeo, Lancia, Chrysler, Dodge, Jeep vehicles and also some Ducati bike models" — Maserati is not named. No sourced basis for A5/A6 (or any other cable) applying to a Grecale, despite the shared Giorgio hardware. | CONFIRMED (that Maserati is absent from MES's own brand list) / UNKNOWN (what that means for Grecale specifically) | https://www.multiecuscan.net/ (fetched 2026-10-14) |
| Module list per bus, with addresses | None published that this pass found | UNKNOWN | — |
| Legislated addressing (11- vs 29-bit) | The North American OBD-II mandate (SAE J1979 / ISO 15765-4) requires a legislated generic-scan pair at 11-bit addressing (`7DF` request, `7E8`-`7EF` replies) on any CAN-equipped vehicle sold there — a general regulatory fact, not Grecale-specific confirmation of which modules actually answer on it | CONFIRMED (general rule) / UNKNOWN (Grecale-specific behavior) | https://en.wikipedia.org/wiki/CAN_bus (fetched 2026-10-14) |

Queries tried and exhausted this pass: "Maserati Grecale security gateway
module OBD diagnostic port CAN bus AlfaOBD"; "Grecale OR Purosangue
multiecuscan.net supported vehicle". A Sidecar/clutch.engineering page
titled "OBD-II support for Maserati Grecale" turned up in search results but
was not fetched (budget) — flagged as the next lead, likely generic PID
coverage rather than UDS bus topology.

---

## Levante (M161, Ghibli/Quattroporte-VI-derived)

| Point | Finding | Confidence | Source |
|---|---|---|---|
| Chassis code | "M161" is the Levante's own internal platform/chassis designation | CORROBORATED (two independent commercial listings, same code) | perdieselsolutions.com "Maserati Levante M161 2017-2020 Workshop Manual" ; cars-technical.com "Maserati Levante Workshop Service Repair Manual" (both fetched via search 2026-10-14) |
| OBD pins 6/14, 3/11, 12/13 | Not found | UNKNOWN | — |
| Bitrates | Not found | UNKNOWN | — |
| Security gateway present, location, model year | A search summary claimed an SGW "above the scuttle panel near the steering column" requiring "specialized bypass plugs" — again a search-tool synthesis, not a verified quote. A promising lead, a Ghibliforum.com thread titled "OBDstar security gateway location" (2026, exact date not retrieved), redirected through a `tollbit.ghibliforum.com` bot-paywall that this pass could not get past within budget — left as an open lead, not used as a source. | UNKNOWN | Lead only: https://www.ghibliforum.com/threads/obdstar-security-gateway-location.39226/ (unreachable this pass) |
| Bypass cables (MES A5/A6 or other) | Same finding as Grecale: Maserati is absent from MultiEcuScan's own supported-brand list | CONFIRMED (absence from list) / UNKNOWN (what it means for Levante) | https://www.multiecuscan.net/ (fetched 2026-10-14) |
| Module list per bus, with addresses | None published that this pass found | UNKNOWN | — |
| Legislated addressing | Same general 11-bit SAE J1979/ISO 15765-4 fact as Grecale | CONFIRMED (general rule) / UNKNOWN (Levante-specific) | https://en.wikipedia.org/wiki/CAN_bus |
| Shared ZF 8HP70 transmission/harness with Ghibli/Quattroporte | Already recorded | CORROBORATED | Already in `mes.platform.PLATFORMS["levante"]`; unchanged this pass |

A second lead, maseratilife.com thread "OBD Scan tool for Levante 2019?",
also redirected through the same `tollbit.*` paywall and was not read.
Queries tried and exhausted: "Maserati Levante CAN bus pinout OBD port
gateway module workshop manual".

---

## Purosangue (Ferrari, all-new platform — not Giorgio, not Chrysler LX)

| Point | Finding | Confidence | Source |
|---|---|---|---|
| Internal chassis/program code | "F175" | SINGLE-SOURCE (one aftermarket tuning-tool vendor page, not cross-checked) | https://www.diagprog4.com/diagprog5-diagnostic-tester-update-2025-new-software-ferrari (fetched 2026-10-14; also names SF90 Stradale as F173, 296 GTB — version 1.0.112, dated 2025-03-31 within that page) |
| OBD pins 6/14, 3/11, 12/13 | Not found | UNKNOWN | — |
| Bitrates | Not found | UNKNOWN | — |
| Security gateway present, model year | Not found. Ferrari is not an FCA/Stellantis-platform car and has no documented relationship to the FCA Serial/Security Gateway Module found for Giorgio-platform cars — no basis to assume one applies | UNKNOWN | — |
| Bypass cables (MES A5/A6 or other) | MultiEcuScan/AlfaOBD's supported-brand list does not name Ferrari at all; this is expected (MES targets FCA-family vehicles) rather than a gap, but is recorded rather than assumed | CONFIRMED (absence from list) | https://www.multiecuscan.net/ (fetched 2026-10-14) |
| Module list per bus, with addresses | None published that this pass found | UNKNOWN | — |
| Legislated addressing | Same general 11-bit SAE J1979/ISO 15765-4 fact | CONFIRMED (general rule) / UNKNOWN (Purosangue-specific) | https://en.wikipedia.org/wiki/CAN_bus |
| Aftermarket scan-tool coverage | Forum chatter (ferrarichat.com "Diagnostic Scan Tool?", 403'd on fetch this pass) and a general note that Launch X431 is reported to work better than most generic tools for Ferrari, on a subscription basis — not independently verified this pass | UNKNOWN (fetch blocked) | Lead only: https://www.ferrarichat.com/forum/threads/diagnostic-scan-tool.712915/ (403, unreachable) |

Queries tried and exhausted: "Ferrari Purosangue OBD diagnostic port CAN
bus security gateway module"; "Ferrari Purosangue diagnostic scan tool
Autel Launch forum security gateway bypass".

---

## What changed in code because of this

* `mes.platform` gained a `BUS_TOPOLOGY` dict (keyed `"grecale"`,
  `"levante"`, `"purosangue"`) and a `bus_topology_for(model)` lookup,
  recording exactly the table rows above — including the `UNKNOWN` ones,
  explicitly, with a `note` explaining why. No existing `PLATFORMS` entry or
  function changed.
* `cuore/live/buses.py` gained `SIBLING_PLATFORM_BUSES` (empty by design —
  no car-specific pin/bitrate fact cleared CORROBORATED this pass) and a
  `sibling_platform_bus(model, bus_key)` lookup that always returns `None`
  today. Giorgio's own `BUSES`/`CAN_C`/`CAN_IHS`/`CAN_CH` are untouched.
  Selection of which car's bus data a live session uses still runs through
  `mes.platform.marque_for_vin()`/`model_for_vin()`, never through this new
  dict, so a Giorgio VIN can never pick up a sibling-platform (non-)entry.

## Follow-ups for the next research pass

1. Fetch the two `tollbit.*`-paywalled forum threads (ghibliforum.com SGW
   location; maseratilife.com Levante OBD scan tool) through a route that
   isn't blocked by that bot-paywall.
2. Read the Sidecar/clutch.engineering "OBD-II support for Maserati
   Grecale" page — likely generic-PID coverage, not UDS/bus topology, but
   unread this pass.
3. Retry ferrarichat.com's "Diagnostic Scan Tool?" thread (403'd) via a
   cached copy or a different thread on the same board.
4. If a real Grecale, Levante, or Purosangue is ever on this bench, a
   passive listen on each OBD pin pair (same method as
   `docs/research/CONNECTIVITY_AND_SGW.md` used for the Stelvio) would turn
   several of these `UNKNOWN`s into `CONFIRMED (local)` in one session.
