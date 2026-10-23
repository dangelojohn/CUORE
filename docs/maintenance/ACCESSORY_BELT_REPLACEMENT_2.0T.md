# Accessory (serpentine / poly-V) belt replacement: 2018 Stelvio 2.0T

Routine-maintenance procedure for CUORE. Written 2026-10-22 from external
references only. **Nothing here is a CUORE reading from this car.** Every
figure carries a source label:

- **official**: FCA/Alfa/Mopar owner's manual, parts catalogue or service information
- **supplier**: an OEM-supplier catalogue listing (Gates, Dayco, Schaeffler/INA/FAG, Contitech), usually seen through a retailer page
- **forum/workshop**: a third-party workshop guide or forum
- **inference**: reasoned from the above, not stated by any source

"Single-source" means exactly one source was found. "Not found, ask dealer /
service info" means no source was found and no value is offered. No torque
value, belt length or part number below is invented.

## 1. Scope and applicability

| Field | Value |
|---|---|
| Vehicle | 2018 Alfa Romeo Stelvio, VIN ZASFAKPN5J7B88115 |
| Engine | 2.0L GME-T4 MultiAir turbo (280 hp NA market / 200 kW), Q4 AWD, ZF 8HP |
| Job | Replace the accessory drive belt. CUORE job `f3ab620b5464` (opened 2026-10-22, owner-attested plan; belt on site) |
| Owner decision on record | Tensioner and idler/pulley wheels are NOT being replaced (owner saw and heard no reason). That is a look-and-listen judgement made without taking the belt off. Section 5 settles it once the belt is off. |

**Applicability caveat (important).** The only step-by-step procedure found is
for the **Giulia 2.0 (2016 on)**, from alfaworkshop.co.uk. The same site lists
the same belt for the Stelvio 2.0 (200, 280 and 350 bhp variants), so the
layout is very probably shared (**inference**). No Stelvio-specific written
procedure was found. Two YouTube walkthroughs for the Stelvio/Giulia 2.0T are
already catalogued in CUORE (`mes-log-mcp/mes/experience.py`, ids
`yt-serpentine-belt-stelvio-2.0l` and `yt-serpentine-belt-giulia-stelvio-2.0t`);
watch one before starting. Photograph the routing on this car before removal
and treat that photo as the authority over any text here.

## 2. When: interval and symptoms

**Interval (official, 2018 US Stelvio owner's manual, Maintenance Plan
footnote 4, PDF p. 218):**

- Areas that are not dusty: recommended maximum 36,000 miles (60,000 km). Regardless of mileage, replace every 4 years.
- Dusty areas and/or demanding use (cold climates, town use, long periods of idling): advised maximum 18,000 miles (30,000 km). Regardless of mileage, replace every 2 years.
- Between replacements the plan has a visual check of the "condition and tensioning of the accessory drive belt(s)" (PDF p. 218), and the "checks to do more often" list for severe use includes "Visually inspect conditions of the accessory drive belts" (PDF p. 216).

CUORE's routine-maintenance list already carries this as `drive_belt`
(36,000 mi / 4 yr, shown overdue on the one-page PDF). Canadian winters, town
use and idling plausibly fall under the demanding-use column (**inference**;
the manual does not classify a given car).

**Symptoms (general practice and workshop sites, not Alfa-specific):**
squeal or chirp on start-up or with A/C on, visible cracking, glazing, missing
ribs or fraying, a belt that runs off-centre, tensioner arm bouncing or
rattling, a charge warning if the belt slips. No Alfa TSB or campaign for
belt, tensioner or pulley noise was found for the 2.0 (see Section 9). A Buick
2.0T belt-noise bulletin turns up online; it is a different engine and is not
evidence for this car.

## 3. Parts and tools

### Belt

| Item | Value | Label |
|---|---|---|
| Mopar/FCA OE number | **68326261AA** | retailer listing (awitalian.com), **single-source** for the Mopar number. CUORE `mes.parts` also lists it, citing giuliaforums. |
| Alfa Romeo (EU) OE number | **50534146**, "Auxiliary belt", 2.0 petrol 200/280/350 bhp, 6 ribs, 6PK1855, "models with air con" | forum/workshop parts shop (alfaworkshop.co.uk), single-source |
| Rib count | 6 (6PK) | alfaworkshop; onlinecarparts.co.uk OE-number page for 68326261AA (6 ribs, 1855 mm, 21 mm wide) |
| Length | 1855 mm (6PK1855) | same two sources |
| Gates | **K060730**: 6 ribs; the listing gives 73.517 in (1867 mm) outside circumference, a different measure from 6PK1855's 1855 mm effective length. Cross-lists Bando 6PK1855 and Alfa OE numbers. Fitment listed 2018-2023 Stelvio. | supplier, via retailer listings seen in search (Gates' own catalogue page not opened). **Single-source: verify at Gates' lookup.** |
| Dayco | **5060730** (RockAuto cross-reference recorded in CUORE `mes.parts`, not confirmed identical); Dayco 6PK1855 under OE 50534146 (alfaworkshop) | supplier |
| Schaeffler / INA / FAG | V-ribbed belt "FB 6PK1856" for Giulia 2.0 (952ABA25B 200 hp, 952ACA25 280 hp) and Stelvio 2.0 Q4 (949.AXA2A) | supplier catalogue via rolling.hu. 1856 vs 1855 is a 1 mm difference; a catalogue rounding difference is likely (**inference**). Compare against the old belt. |
| Other 6PK1855 brands | Contitech, Metzger, Febi, Meyle, Triscan 8640 601855 | retailer listings (autoersatzteile.de, onlinecarparts.co.uk); not individually checked |

**Which number is on the belt on site is not on record.** Record the part
number and brand printed on it (Section 8). If it is not 68326261AA,
50534146, Gates K060730 or a 6PK1855/6PK1856, confirm fit by VIN at a parts
counter.

### Tensioner, idler, alternator pulley (only if Section 5 fails)

| Item | Value | Label |
|---|---|---|
| Deflection/guide pulley | Schaeffler 532 0892 10 | supplier catalogue via rolling.hu, Giulia 2.0 (200 hp and 280 hp variants) |
| Alternator freewheel clutch | Schaeffler 535 0361 10 | same |
| Tensioner part number | not found, ask dealer / service info | |
| Mopar tensioner/idler numbers | not found, ask dealer / service info | |

### Tools (from the Giulia 2.0 guide; Stelvio assumed the same, **inference**)

- Torx T27 driver (19 undertray screws)
- 10 mm socket (plastic auxiliary cover nuts)
- 7 mm socket or driver, a flex driver for the intake hose clamp, and a 7 mm driver for four screws at the top of the air filter housing
- **3/8 in drive breaker bar** (fits the square hole in the tensioner; a long or ratcheting bar helps)
- 22 mm socket for the crankshaft pulley nut, **only to turn the engine by hand** for the rib-seating check. Not a torque operation.
- Torch, camera, clean rag

Torque values: the workshop guide gives **none**, and no source was found for
the tensioner, idler, intake-pipe or cover fasteners: **not found, ask dealer /
service info**. Refit plastic nuts and clamps snug, never hard.

## 4. Safety

- Engine **cold** (exhaust, turbo and coolant parts are close by) and stopped.
- Ignition off, key fob well away from the car (keyless: out of range, ideally in another room) and the car locked, so nothing starts or powers up while hands are near the belt. The car has Start/Stop; do not trust a stop at the lights to mean "off".
- Level ground, parking brake on, in P. If lifting, use stands on the jack points, never the jack alone.
- **Fingers clear of the tensioner and belt run.** A released tensioner springs back hard. Keep the breaker bar under control, release it slowly, and never put fingers between belt and pulley.
- **Battery disconnect: not required** by any procedure found. If it is done anyway: it does not clear stored codes by itself, but it resets learned values and readiness monitors, so the EVAP monitor needs a fresh drive cycle to report ready. This car is already chasing recurring P0455/P0456/P0440, so **record the date and time of any disconnect** as a job action.
- No OBD adapter contact and no code clearing are part of this job.
- Gloves and eye protection; there is overhead work.

## 5. Pre-checks with the belt off

Do these before fitting the new belt. This is where the owner's "tensioner and
idlers are fine" judgement is actually tested. Record each result.

1. **Spin every pulley by hand:** idler/guide pulley, alternator pulley (the freewheel clutch should turn freely one way and lock the other; sticking, grinding or free-spin both ways is a fault), A/C compressor pulley, crankshaft pulley, and the water pump pulley if there is one on the belt (likely, **inference** from a Graf 6-rib, 94 mm pump pulley in a catalogue listing; no Alfa document confirms it). Feel for roughness, noise, wobble or axial play.
2. **Tensioner damping:** move the tensioner arm through its range with the breaker bar. It should move smoothly, resist, and return without sticking, bouncing or free-wheeling. No oil stains, no cracked housing.
3. **Alignment:** sight along the pulley faces for a tilted or offset pulley; read the old belt's wear pattern (one-sided wear points to misalignment).
4. **Grooves:** clean debris out of every pulley rib. Look for rust, glazing, chips or rubber build-up.
5. **Old belt:** photograph cracks, glazing and wear; keep it until the new belt has been proven.
6. If **any pulley is rough**, note it and do **not** fit the belt over it. Order the part (Section 3 numbers are partial; the tensioner number is not found).

## 6. Step-by-step removal and fitting

Steps 1 to 7, 10 and 13 follow the alfaworkshop.co.uk Giulia 2.0 guide
(forum/workshop, not a full workshop manual). Stelvio differences are
possible; verify against your own photos.

**Access.** From below and above. The guide removes the undertray, the plastic
auxiliary cover, and **the turbo air intake pipe must come off** to free that
cover. Wheel-liner removal is not mentioned. The airbox is not removed: only
the four top screws of the air filter housing and the intake pipe.

**Removal**

1. Photograph and sketch the belt routing on the car before touching anything.
2. Remove the undertray: 19 x T27 screws.
3. Facing the front of the car, remove the bottom and top 10 mm nuts on the left of the plastic auxiliary cover, and the middle 10 mm nut on the right (the last nut is about two inches to its left).
4. Loosen the 7 mm clamp on the turbo intake hose with a flex driver (hard to reach). Remove the four 7 mm screws on top of the air filter housing. Push the release tabs to free the two breather pipes from the turbo intake hose. Remove the air intake pipe.
5. Lift out the auxiliary cover.
6. **Release the tensioner.** Put the end of a 3/8 in breaker bar into the square hole on the lower face of the auxiliary tensioner and rotate it **clockwise** to relieve the belt tension. The source mentions no locking pin. The direction as seen from where is not stated: confirm by the arm's own stop (it only moves one way against its spring). A ratchet strap to hold the arm back is common practice, not an Alfa source.
7. Slip the belt off the idler, then work the old belt out from behind the tensioner. Release the tensioner slowly.
8. Do Section 5 now.

**Routing.** No source gives the complete belt path. The driven parts found
in catalogues are: crankshaft pulley (6-rib, driver), alternator with
freewheel clutch pulley, A/C compressor (6 grooves, 119 mm pulley), the water
pump (likely), one fixed deflection (idler) pulley, and the spring tensioner.
The sketch below is a generic memory aid, not the true layout; draw the real
one from your photo.

```
   Generic sketch only (not the true layout):

      [ALT]            [IDLER]
          \             /
   [A/C] ---- belt loop ---- [TENSIONER]
          /             \
   [WATER PUMP?]      [CRANK] (driver, bottom)

   Workshop rule: belt runs OVER the idler; pull the tensioner back,
   then slip the belt UNDER the idler last.
```

**Fitting**

9. Check the new belt: 6 ribs, about 1855 mm, same rib profile as the old belt. Stitching in two places is described as normal by the guide.
10. Route the new belt around crank, compressor, alternator and any other pulleys per your photo, leaving the idler and tensioner for last. Per the guide: route so it runs **over** the idler, pull the tensioner back with the breaker bar, then slip the belt **under** the idler.
11. Release the tensioner slowly. Do not let it snap.
12. Check every rib sits in its groove on every pulley, the smooth back of the belt on any smooth pulley, and that the belt is not twisted.
13. Turn the crankshaft pulley **clockwise** a few times with a 22 mm socket on its nut and confirm the belt tracks true on its ribs (guide).
14. Refit in reverse: auxiliary cover, intake pipe (clamp and both breather pipes), the four housing screws, the cover nuts, the undertray (19 x T27). Torque values: not found, ask dealer / service info; refit snug.

## 7. Post-install checks

1. Rib seating again with a torch after the manual turn (step 13).
2. Start the engine, idle, listen for squeal, chirp, rattle or flutter. Watch the tensioner arm: steady, not bouncing.
3. Switch the A/C on and off at idle and listen again (load changes show slip and tensioner trouble); turn the steering briefly.
4. Dash: no charge warning, no new lamps. Do not read or clear codes as part of this job.
5. **Re-check after a short drive** (about 10 to 20 minutes, then engine off and cool): belt still centred and seated on every pulley, no dust or rubber shavings, no new noise, undertray and intake pipe clamp secure.
6. A new belt may squeak briefly while it beds in. A squeal that persists after the re-check means misalignment, a weak tensioner or a contaminated groove: stop and inspect.

## 8. What to record in CUORE

Add these as actions on job `f3ab620b5464`:

- Belt part number and brand as printed on the belt, and where bought
- **Odometer at install** (no value is on record yet) and the install **date**
- Pulley and tensioner condition from Section 5: each pulley spun / rough / play, tensioner damping, alignment, groove condition
- Whether any battery disconnect happened (date and time)
- Old belt condition (photo)
- **Who fitted it**
- Post-drive re-check result and date

## 9. Known issues and what was not found

- CUORE TSB catalogue (`cuore/data/tsb_catalogue.json`, 140 items): **no** row for belt, tensioner, pulley, alternator or squeal. The only "belt" hit is recall 24V510 (seat-belt buckle switch), unrelated.
- No Alfa/FCA bulletin for accessory-belt noise on the 2.0 was found online either. Ask the dealer on 2026-10-28.
- **Not found, ask dealer / service info:** tensioner and idler part numbers, tensioner/idler/pulley bolt torques, intake-pipe and cover fastener torques, the official routing diagram, a Stelvio-specific written procedure, the release direction as seen from the front, and whether a locking pin is intended.
- Water pump driven by the belt: not confirmed by any Alfa document (inference).
- Mopar 68326261AA is single-source; Gates K060730 was not confirmed at Gates' own site; 6PK1855 and 6PK1856 differ by 1 mm between catalogues.

## 10. Sources

| # | Source | Label | Used for |
|---|---|---|---|
| 1 | 2018 Stelvio Owner's Manual (FCA/Mopar), Maintenance Plan, PDF pp. 216 and 218: <https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf> | official | Interval and severe-use wording |
| 2 | alfaworkshop.co.uk, Giulia 2.0 auxiliary belt replacement: <https://www.alfaworkshop.co.uk/alfa_Giulia_auxiliary_belt_replacement.shtml> | forum/workshop (Giulia 2.0, 2016 on) | Access, tools, tensioner release, routing, rib check |
| 3 | alfaworkshop.co.uk, Stelvio auxiliary belt parts: <https://www.alfaworkshop.co.uk/parts/Stelvio_Auxiliary_Belt.shtml> | forum/workshop parts shop | 50534146, 6PK1855, Dayco, 6 ribs, "models with air con" |
| 4 | awitalian.com, serpentine drive belt 68326261AA: <https://awitalian.com/product/alfa-romeo-giulia-stelvio-serpentine-drive-belt-68326261aa/> | retailer, single-source (blocked on direct fetch this pass; carried from CUORE's earlier record) | Mopar number |
| 5 | onlinecarparts.co.uk, OE 68326261AA: <https://www.onlinecarparts.co.uk/oenumber/68326261aa.html> | supplier listing via retailer (blocked on direct fetch; figures seen in search) | 6 ribs, 1855 mm, 21 mm, Gates/Triscan |
| 6 | Gates K060730 listing: <https://transend.us/products/accessories/accessory-drive-belt-system-components/serpentine-belt/gat-k060730> | supplier via retailer (blocked on direct fetch; seen in search) | Gates cross-reference |
| 7 | Schaeffler catalogue via rolling.hu: <https://shop.rolling.hu/catalog/SCHAEFFLER/alfa-romeo-giulia-952-20-952aba25b> and <https://shop.rolling.hu/catalog/SCHAEFFLER/alfa-romeo-stelvio-949-20-q4-949axa2a> | supplier catalogue via retailer | FB 6PK1856, idler 532 0892 10, alternator clutch 535 0361 10 |
| 8 | NRF catalogue, Giulia 2.0 compressor: <https://webshop.nrf.eu/automotive/air-conditioning-products/compressors/5361-5057.html> | supplier | A/C compressor 6 grooves, 119 mm pulley |
| 9 | CUORE: `mes-log-mcp/mes/maintenance_specs.py` (`drive_belt`), `mes-log-mcp/mes/parts.py`, `mes-log-mcp/mes/experience.py` (two YouTube walkthroughs), `docs/reference/STELVIO_20T_MAINTENANCE_SPECS.md`, `cuore/data/tsb_catalogue.json`, job `f3ab620b5464` | CUORE records | Prior research, videos, TSB search, plan |
