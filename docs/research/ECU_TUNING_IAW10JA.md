# IAW 10JA / GME-T4 Calibration Reference — Alfa Romeo Stelvio 2.0T

**Anchor car:** SW `P235QB39` · SW ver `0000` · HW `MM10JAHW232` · Spare part `50544870` · Drawing `52055320` · Homologation `FIBA00` · ECU ISO `00 01 50 40 18`

**Captured:** 2026-08-27.

---

# 1. Tooling — the decisive finding

## KESS3 supports the MM10JA in **BENCH MODE ONLY**

`CONFIRMED` — Alientech's own release note, upgrade 1.86:

| Brand | Model | Engine | Power | Mode |
|---|---|---|---|---|
| Alfa Romeo | Giulia | 2.0 Turbo 8AT | 147 kW | **Bench** |
| Alfa Romeo | Giulia Q4 | 2.0 Turbo 8AT | 206 kW | **Bench** |
| Alfa Romeo | **Stelvio Q4** | 2.0 Turbo 8AT | **147/206 kW** | **Bench** |

Verbatim: *"MM10JA: RD, WR and Clone in Bench Mode."* — https://www.alientech-tools.com/en/upgrade-1-86/

**206 kW = 280 PS — this car's exact variant, explicitly listed.**

Three consequences that change how you quote the job:
1. **There is no OBD flash path.** The ECU comes out of the car onto a bench harness. Different labour, different risk, different customer conversation.
2. **SGW becomes irrelevant to the flash itself** — the gateway is not in the path when the ECU is on your bench.
3. **Clone is supported**, which is the sanctioned route for ECU replacement without a dealer PROXI dance.

## Editor: ECM Titanium has a dedicated M10JA driver
`CONFIRMED` — https://www.alientech-tools.com/en/drivers-marelli-m10ja-8gm/

Coverage listed: fan and water-pump duty, E85 enrichment, **turbo boost across the three DNA driving modes**, lambda control, ignition timing (race cut limiter), pedal response, start/stop logic — *"three differentiated levels of boost and torque."*

> **That line is the single most useful architectural hint on the platform: boost and torque are tabled *per DNA mode*, not as one global set.** A tune that lifts only one set feels inconsistent to the customer across mode changes.

## File service
**StageX (Magic Motorsport) carries the MM10JA with 306 maps** — `CONFIRMED` as a vendor listing. Parameter groups: *boost pressure, fuel pump management, ignition timing, knock control, lambda control maps, torque limiters, wastegate regulation.*

A mature 306-map pack plus a full ECM Titanium driver is strong evidence the calibration is **well reverse-engineered and not signed.** `LIKELY`

## Tool status summary

| Tool | MM10JA | Confidence |
|---|---|---|
| **Alientech KESS3** | RD/WR/Clone, **bench only** | `CONFIRMED` |
| **Alientech ECM Titanium** | full editor driver, named maps | `CONFIRMED` |
| Alientech K-TAG | not found in reachable release notes | `UNCERTAIN` |
| Magic Motorsport FLEX | site search empty, but their own file service carries the ECU | `UNCERTAIN` — **do not promise this** |
| Autotuner / CMD Flash / Dimsport / BitBox | sites unreachable or 403 | **could not verify** |
| **PCMflash** | full 101-module list fetched — **no Marelli, no FCA/Alfa coverage at all** | `CONFIRMED absent` |
| HP Tuners | no Alfa/Marelli found; their FCA work is Chrysler-domestic | `LIKELY absent` |

**For this shop: the realistic path is KESS3 + ECM Titanium, ECU on the bench.** Everything else is unproven for this ECU.

## Checksum and protection
- **Signing:** no evidence found; the 306-map pack and full editor driver argue strongly against it. `LIKELY unsigned — checksum-protected only.`
- **Checksum:** `LIKELY` conventional multi-region, corrected automatically by KESS3/ECM Titanium.
- **Tuner lock:** `UNCERTAIN`. Alientech's wording (`RD, WR and Clone`, no unlock or virtual-read step) suggests direct memory read rather than a locked bootloader sequence. **Verify on the first read before committing a customer's car.**
- **Rule regardless: take a full ORI read and store it off-machine before any write.** Clone support means a bricked ECU is recoverable from a donor — but only if you have the original.

## Security Gateway
- **Location on Giulia/Stelvio:** LHD — up and right of the steering column, connectors inserted at an angle. RHD — above and left, small press tab needing a pick. `CONFIRMED`
- **What it blocks:** *"you are unable to flash an ECM tune through the OBD port, or clear some codes"* and writing *"data to the various system modules."*
- ⚠️ **Giulia/Stelvio gotcha:** these cars use a **second high-speed CAN bus**, and AlfaOBD warns explicitly: *"please make sure that the bypass supports the second high-speed CAN bus."* **A generic FCA bypass sold for a Ram or Wrangler may leave you unable to reach the chassis modules.** This is the top reason shops report "bypass installed but still can't reach the ABS."
- **AutoAuth** — $5/mo Standard (billed annually), $17.50 PLUS, $42 PLUS CRM. The OEM-sanctioned route; leaves the SGW in place. `street-legal`. Their site does not enumerate supported tools — **verify your scan tool is a certified Tool Partner before subscribing.**
- **Bench flashing sidesteps SGW entirely.** Another argument for the KESS3-bench path.

*This car writes ungated via MES, consistent with a pre-cut-in build. The 02/2018 NAFTA cut-in date could not be independently verified — confirm physically by looking for the module before quoting a job on a sister car.*

---

# 2. Decoding the identifier fields

FCA has never published these encodings. What is structurally certain vs inferred:

| Field | Value | Interpretation | Confidence |
|---|---|---|---|
| Hardware number | `MM10JAHW232` | `MM` = Magneti Marelli, `10JA` = ECU family, `HW232` = hardware rev. `MM10JA` is the exact token Alientech and StageX use | `CONFIRMED` (token) / `LIKELY` (rev) |
| **Software number** | `P235QB39` | **The calibration identifier** — the field that changes between revisions and the one you diff against | `LIKELY` role, `UNCERTAIN` encoding |
| Software version | `0000` | sub-revision counter; `0000` = base issue | `LIKELY` |
| Spare part number | `50544870` | 8-digit orderable FCA part number; `505xxxxx` is Alfa/FCA Italy | `LIKELY` |
| FIAT drawing number | `52055320` | engineering design revision, distinct from the orderable part | `LIKELY` |
| **Homologation number** | `FIBA00` | **Encodes market and emissions standard — the field that matters legally** | `LIKELY` |
| ECU ISO code | `00 01 50 40 18` | raw ISO 14229 identification block; `50 40` plausibly relates to the `5054...` family, `18` to MY2018 | `UNCERTAIN` |

## The method that actually works
Do not try to decode `P235QB39` from first principles.

1. **Log software number + version against VIN, build date, market and homologation on every 10JA car you touch.** MES logs already capture this. Ten cars in and you have a private revision map nobody else has.
2. **Take a full ORI bench read of each distinct software number** and store it. FCA publishes no calibration release notes to independent shops — this is your only revision archive.
3. **Binary-diff two ORIs with the same hardware but different software numbers.** With the ECM Titanium driver loaded you diff at *map* level, not byte level — which turns a diff into an engineering answer.
4. ⚠️ **`FIBA00` is the fork indicator.** Two cars with the same hardware but different homologation codes are **different emissions calibrations and must never share a flash file**, however similar the software numbers look. `emissions-relevant`
5. Cross-check the spare part number for supersessions — an FCA supersession usually signals a change the field never hears about.

---

# 3. What is calibratable — with legal status

| Area | Available | Notes | Legal |
|---|---|---|---|
| **Boost targets** | Yes — **per DNA mode, three levels** | Raising only one set produces inconsistent feel | `emissions-relevant — jurisdiction-dependent` |
| Wastegate regulation | Yes | Pair with boost targets or you fight the closed loop | `emissions-relevant` |
| **Torque model & limiters** | Yes | **The real gate.** Caps what boost can deliver, and protects the 8AT and Q4 driveline | `emissions-relevant`; raising past OEM = driveline exposure |
| Pedal / throttle mapping | Yes | ⚠️ Interacts with §5 — Race mode forces the **N** throttle map regardless of DNA position | `street-legal` |
| Ignition timing | Yes, incl. race cut limiter | | `emissions-relevant` if it moves catalyst protection or knock strategy |
| **Knock control** | Yes | ⚠️ **Do not soften knock retard.** GME-T4 leans on it heavily — this is the most common way a "safe" Stage 1 becomes a rod bearing | `emissions-relevant` |
| Lambda / AFR, incl. deactivation | Yes | Vendor frames it as supporting sports exhausts. **This is catalyst/O2 monitor defeat** | **`competition/off-road only` — unlawful to install on a US road vehicle (CAA §203(a)(3)); voids EU type approval** |
| Rev limiter | Yes | | `street-legal`; durability decision, not a legal one |
| Speed limiter | Yes | | `street-legal` US; EU removal can affect type approval and tyre-rating compliance |
| Launch / creep | not named by either vendor | `UNCERTAIN` | — |
| Exhaust valve control | not in the ECM driver | Body/chassis-controlled on Giorgio — a **coding** job, not a flash job | `street-legal` (noise regs apply) |
| Cat / EGR / EVAP deactivation | Yes | | **`competition/off-road only` — unlawful to install on a US road vehicle; voids EU type approval** |
| Pops & bangs | Yes | Injection cut-off; raw fuel and late combustion into the exhaust | **`competition/off-road only`** — damages catalysts, breaches EU R51 and US state noise law |
| Start/stop deactivation | Yes | **Prefer the body-coding route in §5** — reversible, and does not touch the certified engine calibration | `emissions-relevant — jurisdiction-dependent` |
| Cold-start noise deactivation | Yes | ⚠️ **This is catalyst light-off strategy. Do not touch on a road car.** | `emissions-relevant` |
| E85 enrichment | Yes | US conversion needs EPA/CARB compliance to be road-legal | `emissions-relevant — jurisdiction-dependent` |
| Fan / water pump duty | Yes | Genuinely useful and low-risk — earlier fan-on for track work | `street-legal` |

> **Counter summary:** boost, torque, timing, pedal, rev limit and fan control on an otherwise-stock emissions system are the defensible zone. Lambda / cat / EGR / EVAP / cold-start / pops-and-bangs is **defeat-device territory in the US** and **type-approval-voiding in the EU** — `competition/off-road only`, and in the US it is unlawful to *install*, not merely to sell.

---

# 4. Gains and limits — be skeptical, including of these numbers

## What is actually evidenced

**The only power figure verifiable from any source is a piggyback vendor's marketing claim.** Burger Motorsports JB4, $599, 2017+ Giulia/Stelvio 2.0T: *"Power gains are up to 40hp to the wheels (55hp crank) on a completely stock car on pump gas."* `UNCERTAIN — vendor marketing`

Note the tells: **"up to"**, and a crank figure back-calculated from a wheel figure using an assumed drivetrain loss. On a Q4 AWD 8AT that assumption does a lot of work.

> **No independent dyno figure for a flash tune on the 280 PS GME-T4 could be verified from any credible source. Treat every advertised stage figure as marketing until you put one on your own dyno.**

## What is structurally reasonable

The 206 kW (280 PS) engine is the **high state of tune** of a family whose base is 147 kW (200 PS) — the same hardware spans a 40% factory spread. Two consequences:
- Turbo and fuelling have real headroom at 200 PS, **much less at 280**. Stage 1 gains on the 280 will be proportionally smaller than the internet's Giulia-2.0-base numbers suggest. `LIKELY`
- A Stage 1 claiming the same +50 hp on a 280 as on a 200 is comparing different baselines. `LIKELY`

**Realistic expectation:** the **torque fill between roughly 2000-4000 rpm is where the customer actually feels it**, not peak. Peak is turbo-constrained. No number is given here because none could be verified.

## Where it breaks — order of concern, not thresholds

⚠️ **No failure threshold could be verified for any component** — no turbo limit, no injector duty ceiling, no HPFP flow, no torque converter capacity, no Q4 transfer case or driveshaft rating. **Anyone quoting a precise "the transfer case lets go at X" is repeating folklore unless they cite a Magna spec sheet.**

Correct order of concern, from engineering structure:

1. **Torque limiters and the ZF 8HP.** The TCM has its own torque model and will pull torque if the engine requests more than its map allows. A tune that raises engine torque without addressing this produces **torque-limiter cut, not power**. The TCM is a **separate flash job** — and per `TRANSMISSION_ZF8HP_Q4.md`, no productised TCU tuning exists for Giorgio.
2. **Magna Q4 transfer case** — the front-drive path is the least-oversized element and the most commonly cited practical ceiling. `UNCERTAIN` — treat as limiting until proven otherwise.
3. **Turbo** — at 280 PS the OEM unit is near its efficient limit; more boost buys heat, not air.
4. **Fuel system** — on GDI the HPFP is usually the ceiling before the injectors. **Watch fuel rail pressure deviation under sustained load; that log channel is the real limit indicator, not a spec sheet.**
5. **Driveshafts / halfshafts** — generally last, and typically fail from shock loading, not steady-state torque.

> **Log rail pressure, per-cylinder knock retard, and torque-limiter intervention flags on every tuned car.** Those three channels tell you where *this* car's limit is — the only limit that matters.

---

# 5. ⚠️ The P1CEA purge-ejector trap — read this one carefully

**GME-T4 runs a dual-path evaporative purge.** Off-boost, purge flows conventionally to the intake manifold. **Under boost the manifold is pressurised, so purge is drawn through a second path by an ejector/venturi tee fed from the charge-air-cooler duct**, with a check valve preventing reverse flow. The tee is the only thing making purge work at positive manifold pressure.

A documented P1CEA case on this engine family traced to an **aftermarket intake kit with a missing or defective boost-purge T-junction check valve**.

**Why this will bite the shop — with evidence.** The BMS Performance Intake for Giulia/Stelvio 2.0T ($139) parts list, verbatim:

> *"(1) Renewable inverted cone performance air filter (R0818), (1) Aluminum heat shield, (2) M6x1.0x16mm bolts, (2) M6 nuts, (4) M6 washers."*

**No purge line, no tee, no check valve, no CAC-duct fitting appears anywhere in the product description or install notes.** `CONFIRMED`. The vendor describes it as *"fully reversible"* and *"takes only minutes"* — exactly the framing that leads an installer to leave a purge tee dangling.

> **Shop rule: on any GME-T4 with an aftermarket intake, physically verify the boost-purge tee is reinstated, correctly oriented, and the check valve holds in the correct direction — before chasing any EVAP code and before flashing anything.**
> A tune will not fix it, and an EVAP-deactivation map will *mask* it, which is both the wrong fix and `competition/off-road only`.

Also relevant to tuning validation: **a purge fault throws fuel-trim noise that corrupts any datalog.** Fix the plumbing first.

## Supporting hardware

| Item | Calibration needed? | Legal |
|---|---|---|
| Intake | mechanically plug-and-play — **but see the purge trap above** | `street-legal` if all emissions plumbing is retained |
| Intercooler | none; enables holding boost longer | `street-legal` |
| Downpipe, catted | advisable (O2 monitor readiness) | `emissions-relevant`; US needs EPA/CARB EO |
| Downpipe, catless | requires lambda/cat-monitor changes = defeat device | **`competition/off-road only`** |
| Cat-back exhaust | none | `street-legal` subject to noise limits |

---

# 6. Diagnostic-side coding — highest value, lowest risk

None of this touches the certified engine calibration.

## Tooling
- **MultiEcuScan** — Giulia/Stelvio work with the **MS package without additional adapter cables**; REGISTERED/MULTIPLEXED include Reset/Programming (FREE does not). Community guidance specifies the **blue #5 and grey #6 cables**, with the **grey required for the Continental MK C1 ABS module**. `CONFIRMED`
- **AlfaOBD** — Giulia 2015+ / Stelvio 2016+ need **OBDLink MX+ or EX plus the grey adapter** for the second high-speed CAN bus. `CONFIRMED`
- **Raw byte editor:** MES exposes it via **Ctrl+Alt+C on the Adjustment tab**.

## The verified byte dictionary
All in **Body / CAN Setup** unless noted.

| Feature | Byte | Bits | Values | PROXI alignment after? |
|---|---|---|---|---|
| **Race Mode** | 88 | — | `AC` OEM · `CC` Type 2/DNA · `EC` Type 3/Sport | **Yes** |
| Adaptive Cruise | — | — | Cruise → disabled, ACC → ACC+ | **Yes** |
| Paddle shifter EU/US | 156 | 4-5 | `xx00xxxx` EU · `xx01xxxx` US | **Yes** |
| Window comfort (one-touch) | 58 | 1 | `xxxxxx0x` off · `xxxxxx1x` on | Yes* |
| **Battery type** | 63 | 0-3 | codes below | **No** |
| Seat belt chime | Dashboard/IPC → Adjustments | — | GUI setting | **No** |
| TPMS pressure references | Body / RFHub | — | front/rear values | **No** |

\* MES ≥ 4.7 exposes this in the GUI and needs no alignment; earlier versions need byte editing and do.

**Battery type codes (byte 63):** `xxxx0001` 80Ah 680A (EU default) · `xxxx0010` 95Ah 800A (US default) · `xxxx0011` 80Ah 680A diesel · `xxxx1000` H7 flooded · `xxxx1001` H7 AGM · `xxxx1010` H8 flooded · `xxxx1011` H8 AGM (MY20 default).

> **Battery type is the sleeper high-value job.** No PROXI alignment, five minutes, fully reversible — and setting it correctly after an AGM upgrade fixes the charging-strategy and start/stop behaviour that otherwise generates repeat "battery warning" comebacks.

## Race Mode on a non-QV — the flagship job

1. **Hardware (pre-2020 only):** the DNA selector must become DNA+R — fit a Quadrifoglio RDNA selector, or modify the existing one with a **147-ohm resistor and a micro-switch**. **2020+ monostable selectors skip this entirely.**
2. **Coding:** byte 88 `AC` → `CC` or `EC`, then PROXI alignment.

**What actually changes:** ESC intervention reduced, FCW disabled, and — **often not mentioned by people selling this** — **throttle defaults to the Normal map regardless of DNA position.** Set expectations: this is a stability-control and chassis change, not a power or throttle change.

**Known blocker:** older CDCM firmware may refuse the configuration; **upgrading the CDCM to version 501+** may be required.

**Legal:** `street-legal` in most jurisdictions, but it **disables Forward Collision Warning** and reduces ESC authority. In the EU, ESC is mandatory under Reg. (EC) 661/2009 — defensible as an OEM-provided mode since it exists on the QV, but disabling FCW on a car type-approved with it is a grey area. **Document the customer's request in writing** — the liability exposure if they have a collision with FCW coded off is real, and it is yours.

## PROXI alignment — the discipline

Required whenever you change a parameter with **no dedicated adjustment item** — i.e. anything edited at byte level.

Procedure: connect to the **Body** module, run PROXI alignment, **switch cables when prompted.** Then three follow-up calibrations, all on the **Continental MK C1 ABS module (grey #6 cable)**:
1. Steering angle reset
2. Lateral and longitudinal acceleration sensor calibration
3. Pressure sensor calibration

Then **cycle the steering wheel full-lock to full-lock after restart** to clear remaining warning lamps.

Two warnings, verbatim from the source:
> *"Without proper COM port settings, you may end up failing the PROXI alignment. READ THE MANUAL."*
> *"Pay close attention and only alter what you are attempting to alter as these settings can have dire consequences if changed unknowingly."*

> ⚠️ **Non-negotiable shop procedure: dump the full PROXI data to a text file before any modification.** That file is your only restore path — the difference between a five-minute revert and a dealer visit.

## Reversibility summary
- **No alignment, trivially reversible:** battery type, seat belt chime, TPMS references, window comfort on MES ≥ 4.7.
- **Alignment required, still reversible:** Race mode, adaptive cruise, paddle shifter, after-wipe, window comfort on older MES. Every revert costs another full alignment plus the three ABS calibrations — **batch changes; don't spread them across three visits.**
- **Hardware-gated:** Race mode pre-2020 needs the physical DNA+R selector.

---

# 7. Could not verify

1. The encoding of `P235QB39`, and any FCA calibration changelog.
2. Confirmation that `50544870` is the ECM part number — catalogue lookup 404'd.
3. **The exact FCA definition of P1CEA** — every DTC database URL 404'd. The mechanism in §5 is architecturally sound; the code mapping is shop-supplied.
4. The 02/2018 NAFTA SGW production cut-in date.
5. **Checksum, tuner-lock and signing status** — inferred, never confirmed. **Verify on the first bench read.**
6. MM10JA support in Magic FLEX, Autotuner, CMD Flash, Dimsport, BitBox, K-TAG. **Only KESS3 is confirmed.**
7. **Any independent dyno data** for Stage 1 or 2 on the 280 PS engine. None exists publicly.
8. **Every mechanical failure threshold.** No manufacturer spec reachable for any component. **Do not repeat forum numbers as fact.**
9. Whether launch control and exhaust valve control are calibratable in the ECM.
10. Whether AutoAuth supports this shop's specific scan tools.

*Note: this research ran while the session's web-search budget was exhausted, so it relied on direct fetches against known vendor URLs. Items 1, 3, 4, 6 and 7 are the most likely to resolve quickly now that search is restored.*

**Sources:** alientech-tools.com (upgrade 1.86; M10JA driver page) · stagex.ai/eculist/details/1062 · alfaobd.com · multiecuscan.net · giuliatech.com (byte dictionary, SGW bypass, Race mode, PROXI procedures, Competizione TCM flash) · burgertuning.com (JB4; BMS intake parts list) · autoauth.com · pcmflash.ru
