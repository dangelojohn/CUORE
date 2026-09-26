# 2018 Alfa Romeo Stelvio 2.0T — Service Specs

VIN ZASFAKPN5J7B88115. 2.0L GME-T4 MultiAir turbo (sales code EC2), US
market, Q4 AWD, ZF 8HP automatic.

This is the human-readable companion to `mes-log-mcp/mes/service_specs.py`,
which is what `mes.service` and cuore's oil-change / service / brakes-tires
/ torque pages actually read. The two must agree — this file exists so a
person can review the sourcing without reading Python.

**Confidence levels** (never invented — an absent value is recorded as
UNKNOWN, never guessed):

- **CONFIRMED** — an actual manufacturer document (owner's manual, Mopar/FCA
  parts catalog, FCA/Alfa service information, TechAuthority excerpt).
- **CORROBORATED** — two independent non-manufacturer sources agree.
- **SINGLE-SOURCE** — exactly one source found, not cross-checked.
- **UNKNOWN** — nothing credible found. Use the service manual
  (TechAuthority). Never a guess presented as a number.

The 2018 Giulia 2.0T shares this car's engine (and much of its running
gear), so a fair amount below is corroborated from Giulia-specific sources.
Rows that lean on Giulia sourcing say so explicitly — offered as
corroboration, not silently folded in as Stelvio-specific.

Research pass done 2026-09-26 by web search (Mopar/FCA parts listings,
vehicleinfo.mopar.com, stelvioforum.com, giuliaforums.com, alfaowner.com,
alfabb.com, parts/tool sites, tyre-fitment databases) plus this repo's own
`docs/reference/ZF8HP_SERVICE_DATA.md`, which traces to actual FCA/Alfa OEM
service information for this platform. No paywalled FCA/Stellantis
TechAuthority document was reached directly during this pass.

## Oil service

| Item | Value | Confidence | Source | Notes |
|---|---|---|---|---|
| Viscosity | 0W-30 full synthetic | CORROBORATED | [giuliaforums / bobistheoilguy](https://bobistheoilguy.com/forums/threads/alfa-romeo-giulia-oil-fiat-spec-9-55535-gs1.344407/) | 5W-40 (Euro "Selenia" spec, same engine) also reported approved; confirm against the sticker on this car. |
| Spec / approval | FCA/Mopar MS-13340, API SN (2017-18 build); historically Fiat 9.55535-GS1 | CORROBORATED | [giuliaforums](https://www.giuliaforums.com/threads/giulia-2-0l-oil-specifications-sn-versus-sn-plus-and-ms13340.50969/) | Do NOT use MS-12633 (Pennzoil 0W-40 SN) — that's the Quadrifoglio/SRT V6 spec, not this engine's. |
| Capacity with filter | 5.5 US qt (~5.2 L) | SINGLE-SOURCE | [AMSOIL VIN/engine-code lookup](https://www.amsoil.com/lookup/auto-and-light-truck/2018/alfa-romeo/stelvio/2-0l-4-cyl-engine-code-n-ec2-n-turbo/) | Keyed to this exact engine code (N)/sales code (EC2). Disregard aggregator pages quoting 5.5-7.4 qt — that blends the 2.0T and 2.9L V6. |
| Filter (Mopar) | 4892339 (suffix revised over production: BE / AB / AC) | SINGLE-SOURCE | [giuliaforums](https://www.giuliaforums.com/threads/oil-filter-2-0-part-number-change.49369/) | Do NOT use 68191349AA/AC — that's the V6 filter family. Confirm current suffix at a Mopar counter by VIN. |
| Filter (aftermarket cross-ref) | UNKNOWN | UNKNOWN | — | No confidently-sourced Mann/Bosch/K&N cross-ref found. Cross-reference the Mopar number at a parts counter. |
| Drain plug part / washer | UNKNOWN | UNKNOWN | — | One source describes a built-in/captive rubber gasket rather than a separate crush washer — if true, the whole plug may need replacing to renew the seal. A washer PN (670050349) is documented for the Quadrifoglio V6 only — do not assume fitment. |
| Service interval | 8,000 mi / 12 months, whichever first | CORROBORATED | [giuliaforums "Oil Change Frequency"](https://www.giuliaforums.com/threads/oil-change-frequency.47281/) | Conventional oil explicitly NOT approved for this turbo engine. Owners report shortening to 5,000-6,000 mi for short-trip/stop-and-go/hard driving. |
| Oil-life reminder behaviour | Algorithmic oil-life monitor on top of the fixed interval | SINGLE-SOURCE | [stelvioforum reset thread](https://www.stelvioforum.com/threads/alfa-romeo-stelvio-giulia-oil-change-maintenance-reset.19336/) | Reset via MES (fastest, reported reliable), wiTECH (IPC > Misc Functions > Maintenance Reset), or an unofficial accelerator-pedal-pump procedure (inconsistent across software revisions). |

## Torque library (selected — see the searchable `/v/{vin}/torque` page or
`mes.service_specs.TORQUES` for the full table with every category)

| Fastener | Value | Confidence | Notes |
|---|---|---|---|
| Oil drain plug | 20 Nm | SINGLE-SOURCE | Described as having a built-in rubber gasket; easy to overtighten past this into the pan threads. |
| Oil filter housing cap (cartridge filter) | 25 Nm | SINGLE-SOURCE | Cartridge filter under a screw-on **plastic** housing cap, not a spin-on canister — do not overtighten. |
| Wheel lug bolts | 121 Nm (89-90 ft-lb) | CORROBORATED | **Bolts** threaded into the hub, not nuts on studs. A third source reports 110 Nm for "14mm bolts" — confirm fitment before trusting either figure; safety-critical. |
| Spark plugs | 19.5 Nm (19-20 Nm range) | CORROBORATED | Giulia-sourced (same engine). Do not stack anti-seize unless the plug maker calls for it. |
| Undertray / splash-shield fasteners | UNKNOWN | UNKNOWN | Typically plastic push-pin/screw retainers, hand-tight; any structural metal bolts should follow TechAuthority. |
| Front brake caliper guide/slide bolt | 30 Nm | CORROBORATED | Brembo-fitted cars (Giulia-sourced); apply medium-strength threadlocker. |
| Front brake caliper bracket bolt | UNKNOWN | UNKNOWN | Conflicting forum figures (~77 Nm vs ~104 Nm) that do not corroborate each other — do not pick one; use TechAuthority. |
| Rear brake caliper guide/slide bolt | 27 Nm (26-28 range) | SINGLE-SOURCE (low confidence) | Read via a search-summary only, paywalled thread; unclear which exact fastener. Rear caliper carries the EPB actuator — service mode required first. |
| Rear brake caliper bracket bolt | UNKNOWN | UNKNOWN | Not distinguished from the guide bolt in any source found. |
| Rotor retaining screw | UNKNOWN | UNKNOWN | Confirmed M10x1.25 thread from parts listings; no torque value found. Easy to snap/strip. |
| Ignition coil pack bolt | UNKNOWN | UNKNOWN | — |
| EVAP canister / ESIM mounting | UNKNOWN | UNKNOWN | Directly relevant to this VIN's current P0440/P0455/P0456 diagnosis. |
| EVAP purge valve mounting | UNKNOWN | UNKNOWN | — |
| Battery terminal / hold-down | UNKNOWN | UNKNOWN | Do not substitute a generic figure — overtightening cracks the terminal post. |
| Sway bar end link, front/rear | UNKNOWN | UNKNOWN | — |
| Tie rod end nut | 92.5 Nm (90-95 range) | SINGLE-SOURCE | May be the INNER tie rod (rack), not the OUTER end a suspension job usually disturbs — confirm which joint. |
| Upper control arm to knuckle | 51 Nm | SINGLE-SOURCE | Reference only — lower control arm (the one actually asked for) is UNKNOWN. |
| Front strut to lower control arm | 60 Nm + 135° | SINGLE-SOURCE | Torque-to-yield pattern → treated as **single-use** even though no source states that explicitly. |
| Lower control arm to knuckle / to subframe | UNKNOWN | UNKNOWN | — |
| Wheel bearing/hub nut | UNKNOWN | UNKNOWN | Treated as **single-use** — AWD platforms commonly use a high (200+ Nm) torque-to-yield hub nut. |
| ZF 8HP transmission pan/filter bolts (13x) | 10 Nm | **CONFIRMED** | From this repo's `ZF8HP_SERVICE_DATA.md`, traced to FCA/Alfa OEM service information (ZF doc 1087.754.107c). Pan+filter is one integrated, non-separately-serviceable assembly; gasket reusable if undamaged. |
| ZF 8HP drain / fill plug | UNKNOWN | UNKNOWN | No separate drain plug identified for this pan design; see the pan-bolt spec above. Fill is a temperature-controlled (30-50°C) level-plug procedure per `ZF8HP_SERVICE_DATA.md`. |
| Transfer case (Q4) drain / fill plug | UNKNOWN | UNKNOWN | An open question in the community (a stelvioforum thread asks this exact question and gets no answer) — do not assume "same as the diff". |
| Rear differential drain / fill plug | 26 Nm | SINGLE-SOURCE | Stated by a forum poster in the same thread asking about the transfer case. |

## Brakes / wheels / tyres

| Item | Value | Confidence | Notes |
|---|---|---|---|
| Pad minimum thickness, front/rear | UNKNOWN | UNKNOWN | No FCA-specific figure found (forum rule-of-thumb ~2-3mm is not a manufacturer spec). Car has an electronic pad-wear sensor on the inner pad. |
| Rotor new thickness, front/rear | 28 mm / 22 mm | SINGLE-SOURCE | Aftermarket aggregator (go-parts.com), not a manufacturer document. |
| Rotor minimum thickness, front | 25.5 mm | SINGLE-SOURCE | Same source; not cross-checked. Read the cast-in "MIN TH" marking on the physical rotor as the most reliable check. |
| Rotor minimum thickness, rear | UNKNOWN | UNKNOWN | The source giving the front figure explicitly says no rear figure is published. |
| Rotor max runout | UNKNOWN | UNKNOWN | — |
| Brake fluid | DOT 4 | SINGLE-SOURCE | Forum consensus, no Mopar document located. FCA has spec'd DOT 4 Low Viscosity on some contemporaneous EPB platforms — confirm against reservoir cap markings. |
| Fluid change interval | ~24 months | SINGLE-SOURCE | Forum rule of thumb tied to moisture absorption, not a quoted FCA interval. |
| OE tyre, 18" base | 235/60R18 | CORROBORATED | Multiple independent fitment databases agree. Read this VIN's actual fitment off the door placard. |
| OE tyre, 19" Ti option | 235/55R19, 101V | CORROBORATED | Staggered fitment applies to the Quadrifoglio, not the base 2.0T. |
| Tyre pressure, front/rear | 30 psi (207 kPa) / 33 psi (228 kPa) | SINGLE-SOURCE | Reported for the 19" fitment; the Mopar placard PDF found was image-based with no extractable text. **Read the actual door-jamb placard on this VIN** — no reliable figure found for the 18" base fitment specifically. |
| Rotation pattern | Square fitments: standard rotation. Staggered (Quadrifoglio / any car actually fitted with different front/rear sizes): DO NOT ROTATE | SINGLE-SOURCE | Inferred from consistent single-size fitment-database listings for the base 2.0T; no explicit FCA statement found. |
| EPB service mode (rear) | Infotainment: Settings > Passive Safety > Brake Service Mode, ignition on/engine off, in Park, foot brake released | SINGLE-SOURCE | Never force the rear piston back mechanically without service mode active — can strip the actuator. Press pistons straight back (no rotation — tears the seal). |

## Live TPMS (read-only)

The RFHUB module answers UDS DIDs `40B1`–`40B4` (one per corner: FL, FR, RL,
RR) with pressure/temperature — see `cuore/live/addressing.py` and
`cuore/live/did_catalog.py`. The brakes/wheels/tyres page shows the latest
matching observation from `mes.live_obs` if one has already been recorded;
it never triggers a live read itself.

## What's still UNKNOWN and needs TechAuthority

Front caliper bracket bolt, rear caliper bracket bolt, rotor retaining
screw, coil pack bolt, EVAP canister/ESIM/purge-valve mounting, battery
terminal/hold-down, sway bar end links (front and rear), lower control arm
bolts (to knuckle and to subframe), wheel bearing/hub nut torque, ZF 8HP
drain/fill plug, transfer case drain/fill plug, rear pad/rotor minimum
thickness, rotor max runout, and the 18" base tyre pressure specifically.
None of these were invented — each is recorded as UNKNOWN in
`mes.service_specs` with a pointer to the service manual (TechAuthority).


## Fact-check corrections (2026-09-26)

- **Front strut to lower control arm bolt**: the previously listed 60 Nm + 135 deg is WITHDRAWN. The cited go-parts.com article publishes no torque value. UNKNOWN: use the service manual (TechAuthority). Treat the bolt as single-use.
- **Upper control arm to knuckle bolt**: the previously listed 51 Nm is WITHDRAWN for the same reason. UNKNOWN.
- Rotor dimensions now cite the actual go-parts.com rotor article, not the site root.
- Brake fluid, fluid interval, tyre sizes, tyre pressures and rotation rows now name their (non-manufacturer) sources instead of none.

- **Oil interval** (2026-09-26): the 2018 US owner's manual (Mopar-hosted PDF) sets the limit by the dash indicator, never more than 1 year / 10,000 mi (16,000 km); severe duty 4,000 mi. cuore keeps 8,000 mi / 12 mo as the conservative shop interval.
- **Brake fluid interval** is now CONFIRMED: every 2 years regardless of mileage (owner's manual note 6).
