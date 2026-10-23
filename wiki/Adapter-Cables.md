# Adapter Cables

A catalogue of the coloured OBD adapter cables sold for MultiEcuScan (MES), FiatECUScan and AlfaOBD, with the pin maps, buses and vehicles that vendors and forums describe for each.

**External reference, not a CUORE reading.** Everything on this page was gathered from vendor listings, official tool pages and owner forums on 2026-10-22. None of it was measured on the reference car and none of it is proof. Each row keeps its own confidence grade and sources. Products are mentioned as what a document records; none is endorsed here.

Full text: `docs/research/ADAPTER_CABLES.md`. Data: `cuore/data/adapter_cables.json`. Read-only views: `GET /api/cables` (optional `?brand=`) and the `/cables` page. See [[Hardware and Cables|Hardware-and-Cables]] for what CUORE itself uses.

## Cautions first

- **Wrong-bitrate listens.** Never open a bus at a rate other than its own. On 2026-10-14 three receive-only windows of about 2 s each on CAN-CH at 250 kbit/s and 125 kbit/s lit the **airbag lamp with a chime** on the reference car. CAN-CH is 500 kbit/s only; CAN-IHS is 125 kbit/s only. A catalogue row with a blank or "not stated" bitrate is never a licence to try a rate.
- **Pins 1 and 9.** Never short pins 1 and 9 on Giulia or Stelvio; it drops the bus. The green A1 lead ties pins 1, 7, 9 and 12 together, so it must not be fitted to these cars. Continuity-check any cable before fitting. (The public sources found name other models in their short-circuit warning, not Giulia or Stelvio; the project rule follows from the mechanism.)
- **Only two cables are driven live.** CUORE has routes for the **blue A5** (`blue_a5`, CAN-IHS, pins 3/11) and the **grey A6** (`grey_a6`, CAN-CH, pins 12/13) only, and only those two are confirmed on the reference car. Every other row is reference data: CUORE has no route for it and the catalogue adds none.
- **Contradictions exist.** Vendors disagree: some listings call blue "Control unit" and grey "Basic control unit", and one 6-piece page labels grey as "Adapter 5". Check continuity rather than trusting a colour.

## Summary table

| ID | Colour | Car pins to tool pins | Bus | Bitrate | CUORE live | Confidence |
|---|---|---|---|---|---|---|
| A1 | green | tool 7 to car 1, 7, 9, 12 | K-line | not stated | no | official (models) + listing (pins) |
| A2 | red | tool 7 to car 3 | K-line (airbag) | not stated | no | official (models) + listing |
| A3 | yellow | tool 6 to car 1, tool 14 to car 9, tool 7 to car 12 | Low-speed CAN (+ K pin 12) | not stated | no | official + listing |
| A4 | purple | tool 7 to car 7, 8, 11, 13 | K-line (pin 13) | not stated | no | listing-only (+ MES tag) |
| **A5** | **blue** | tool 6 to car 3, tool 14 to car 11 | MS-CAN / BHCAN (project: CAN-IHS) | 125 kbit/s (listing) | **yes, `blue_a5`** | official (tags, "middle-speed CAN") + listing + forum |
| **A6** | **grey** | tool 6 to car 12, tool 14 to car 13 | second high-speed CAN (project: CAN-CH) | 500 kbit/s per project; in no source read | **yes, `grey_a6`** | official + listing |
| 3-pin | not stated | 3-pin round to OBD-II | K-line | not stated | no | official (models) + listing + forum |
| SGW 12+8 | n/a | replaces the SGW connectors | all CAN behind the gateway | not stated | no | official notes + listing |
| Fuchs multi | not stated | not stated | not stated | not stated | no | listing-only |
| White, black, orange, Adapter 7+ | | | | | no | not found |

"Tool X to car Y" follows one vendor's phrasing: the tool end pin X connects to the car end pin Y. Pin 6/14 on the tool side is where the adapter listens; the cable moves another bus onto it.

## Per-brand and platform matrix

| Platform | What the sources say is needed | Source basis |
|---|---|---|
| Giorgio Alfa (Giulia 2015+, Stelvio 2016+, Tonale) | Standard CAN 6/14: no cable. Blue A5 (3/11): infotainment and body. Grey A6 (12/13): ABS, airbag, steering, and others. 2018+: an SGW bypass that also carries 12/13 | official + listing |
| Older Alfa | K-line cars (147, 156, 159, GT, Brera): green (+ red). Mito, Giulietta, 4C: yellow. Early cars: 3-pin | official (AlfaOBD) |
| Maserati (Ghibli, Quattroporte, Levante) | AlfaOBD lists OBDLink MX+/EX only, no coloured cable. MES: not a supported make. One vendor's SGW bypass listing names Ghibli and Levante. Grecale, MC20: no source found | official (AlfaOBD) / not found |
| Ferrari | No MES or AlfaOBD support found. Older 3-pin cars use K-line on the 3-pin; owner-derived pins only | forum |
| Fiat / Abarth | Old K-line: green, red, 3-pin. Low-speed CAN (500, Punto, Panda, Doblo, Ducato X290, Abarth): yellow. 500X, 500e 2020+, Toro, Argo/Chronos, Ducato Serie 8: grey (MES blue on 500X, 500e, Egea) | official |
| Jeep / Ram / Chrysler / Dodge | Renegade 2014+, Compass MP 2017+, ProMaster 2022+: grey. ProMaster pre-2022 and City, Chrysler Ypsilon: yellow. MES tags put blue A5 on Thema, Freemont, Journey, Neon 2016 | official |

Some adapters make the colour cables unnecessary: AlfaOBD states that certain interfaces multiplex the 3/11 pins themselves, and MES states its multiplexed packages need no extra adapters except the 3-pin. The vLinker FS that CUORE uses is among the interfaces AlfaOBD lists that way, yet on the reference car the cables are what reach CAN-IHS and CAN-CH ([[Hardware and Cables|Hardware-and-Cables]]).

## Security Gateway

On 2018+ cars the SGW blocks actuator tests and code clearing. MES states it cannot unlock the SGW module. A vendor sells a 12+8 bypass lead for Giulia and Stelvio 2017+ and others; the listing does not say pins 12/13 are carried. CUORE does not attempt an SGW bypass ([[Hardware and Cables|Hardware-and-Cables]]).

## Sources

Official: alfaobd.com (home page, supported_cars, supported_units), multiecuscan.net (SupportedVehiclesList). Listings: Gendan (FESBLUE, FESGREY, FESYELLOW, FESCBL, LEAD3PIN, SGWBYPASS), Alfissimo, AsTools, Electronic-Fuchs, Obdauto.fr, Squadra Tuning. Forums: Fiat Forum, Team-BHP, FerrariChat, and MES, Giulia Forums and Club Alfa threads quoted only through search summaries because the pages could not be opened. The full URL list, per-row source lists and the method caveats are in `docs/research/ADAPTER_CABLES.md`.

Next: [[Hardware and Cables|Hardware-and-Cables]], [[Vehicle Networks|Vehicle-Networks]], [[Safety Rules|Safety-Rules]].
