# 2018 Alfa Romeo Stelvio 2.0T — Routine Maintenance Specs

VIN ZASFAKPN5J7B88115. 2.0L GME-T4 MultiAir turbo (sales code EC2), US
market, Q4 AWD, ZF 8HP automatic, ~142,290 km.

This is the human-readable companion to `mes-log-mcp/mes/maintenance_specs.py`,
which backs cuore's maintenance pages. It covers the *routine, mostly
owner-schedule* items — filters, spark plugs, coolant, brake fluid, belt,
battery, wipers, fuel filter, PCV, throttle body, boost hoses, washer fluid,
A/C service, power steering, hood/door lubrication. It does **not** duplicate
torque values or oil-change specifics — those live in
`mes.service_specs` (see `STELVIO_20T_SERVICE_SPECS.md`) and
`mes.drivetrain_specs` (see `STELVIO_20T_DRIVETRAIN_SPECS.md`); this module
only *points at* a torque row by key (`torque_keys`) rather than repeating a
number that could drift out of sync.

**Confidence levels** (never invented — an absent value is recorded as
UNKNOWN, never guessed):

- **CONFIRMED** — an actual manufacturer document (owner's manual, Mopar/FCA
  parts catalog, FCA/Alfa service information, TechAuthority excerpt).
- **CORROBORATED** — two independent non-manufacturer sources agree.
- **SINGLE-SOURCE** — exactly one source found, not cross-checked.
- **UNKNOWN** — nothing credible found. Use the service manual
  (TechAuthority). Never a guess presented as a number.

## Primary source: the actual owner's manual

Research pass done 2026-09-26. The single best find this pass was the real
**2018 US Stelvio Owner's Manual**, fetched directly from FCA/Mopar's own
publications host (not a paywalled TechAuthority document — a free, public
PDF):

**<https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf>**

Its "Maintenance Plan (2.0 T4 MAir Engine)" table (pp. 213–217) gives exact,
manufacturer-sourced mileage/year bullet marks for most items below, and its
"Fluid Capacities" / "Fluids And Lubricants" tables (pp. 262–264) give exact
capacities and fluid specs. Every row below marked **CONFIRMED** and citing
this URL was read directly out of that table (column positions were decoded
from the PDF's own word coordinates, not guessed from OCR line-wrapping).
This is a materially better source than the forum/aggregator sourcing used
in the sibling `service_specs.py`/`drivetrain_specs.py` modules, which did
not have this document in hand — those modules have **not** been revised to
match here; where this document conflicts with them, this document wins for
these 17 items, and a note says so.

Secondary sources: Mopar/FCA parts listings (moparonlineparts.com, Mopar
Genuine Parts, alfaromeofiatpartsusa.com), stelvioforum.com, giuliaforums.com,
alfaowner.com, NGK's own part listing, and industry refrigerant-quantity
references (top-refrigerants.com).

## Summary table

| Item | Category | Interval | Confidence | Source |
|---|---|---|---|---|
| Engine air filter | filters | 30,000 mi / 3 yr (10,000 mi if dusty) | CONFIRMED | Owner's manual |
| Cabin air filter | filters | 20,000 mi / 2 yr mandatory (10,000 mi if dusty) | CONFIRMED | Owner's manual |
| Spark plugs | ignition | 30,000 mi, mileage-only | CONFIRMED | Owner's manual |
| Ignition coils (inspect) | ignition | No schedule — symptom-driven | UNKNOWN | — |
| Engine coolant | fluids | 150,000 mi / 15 yr (one-time, long-life OAT) | CONFIRMED | Owner's manual |
| Brake fluid | fluids | 24 months, no mileage | CONFIRMED | Owner's manual |
| Drive (serpentine) belt | engine | 36,000 mi / 4 yr normal; 18,000 mi / 2 yr severe | CONFIRMED | Owner's manual |
| 12V battery | electrical | Charge-status CHECK every 10,000 mi/1 yr; replacement condition-driven | CONFIRMED (check) | Owner's manual |
| Wiper blades | body | ~1 year (no mileage figure) | CONFIRMED | Owner's manual |
| Fuel filter | filters | No schedule — lifetime in-tank unit | CORROBORATED | Forum + owner's manual "if equipped" wording |
| PCV system | engine | No schedule — inspect/replace on failure | UNKNOWN | — |
| Throttle body cleaning | engine | No OEM schedule | UNKNOWN | — |
| Intake/boost hoses (inspect) | engine | No schedule — symptom-driven | UNKNOWN | — |
| Washer fluid | fluids | Top off monthly/600 mi | CONFIRMED | Owner's manual |
| A/C / cabin service | fluids | Annual, "beginning of summer" | CONFIRMED (interval); CORROBORATED (refrigerant charge weight) | Owner's manual + industry chart |
| Power steering (EPS) | fluids | N/A — no fluid, electric only | CONFIRMED | Owner's manual |
| Hood and door lubrication | body | 20,000 mi / 2 yr (hood/liftgate locks only) | CONFIRMED | Owner's manual |

## Item detail

### Engine air filter — CONFIRMED interval
Owner's manual "Replace air cleaner cartridge" row: mandatory every 30,000
miles / 3 years (30k/60k/90k/120k/150k bullet marks), 10,000 miles if used in
dusty areas. Part: Mopar **68301538AA**, CORROBORATED across multiple
retailers and aftermarket cross-references (WIX WA11084, Champion CA12953,
Fram XA10670, PurolatorAir A11523, Premium Guard PA99467) for 2018–2020
Stelvio/Giulia 2.0L non-QV.

### Cabin air filter — CONFIRMED interval, SINGLE-SOURCE part
Owner's manual "Replace the passenger compartment cleaner" row: MANDATORY
every 20,000 miles / 2 years, with a RECOMMENDED interim check/replace at the
in-between 10,000-mile points; 10,000 miles flat if dusty. Part number is
genuinely unresolved — three different Mopar numbers turned up across
retailers (68444656AA, 68392124AA, 68320112AA) with no documented year/trim
split. Confirm by VIN at a parts counter.

### Spark plugs — CONFIRMED interval, CORROBORATED part
Owner's manual: mandatory every 30,000 miles, explicitly **mileage-only**
("Yearly intervals do not apply"). Part: NGK 90219 (ILZKR7G7G) / Mopar
68292346AA, gap 0.028 in (0.7 mm) per NGK's own listing (plugs ship
pre-gapped — verify anyway). Torque: reuses `service_specs.TORQUES['spark_plug']`
(19.5 Nm, CORROBORATED) rather than repeating the figure here.

### Ignition coils (inspect) — UNKNOWN interval
Not in the owner's manual's maintenance plan at all — diagnose on misfire
codes, replace on failure. No part number sourced this pass. Torque key
`coil_pack_bolt` exists in `service_specs.py` but is itself UNKNOWN there.

### Engine coolant — CONFIRMED interval and capacity
Owner's manual marks a **single** mandatory coolant change at 150,000 miles
/ 15 years — a genuinely long-life fill, not a recurring service item.
Capacity: 2.3 US gal / 8.8 L for the **engine** circuit (owner's manual
"Fluid Capacities" table). Important nuance this pass surfaced: the
water-cooled intercooler on this turbo engine has its **own separate**
cooling circuit at 1.4 US gal / 5.25 L, not included in the 8.8 L figure —
do not conflate the two when planning a drain-and-fill. Spec: FCA/Alfa
MS.90032 (CUNA NC956-16, ASTM D3306) OAT, used at 50%, not mixable with other
formulations; 60/40 product/water for harsh climates. No sourced drain-plug
location or bleed procedure for this engine — TechAuthority.

### Brake fluid — CONFIRMED interval (upgrade over service_specs.py)
Owner's manual footnote: "brake fluid replacement has to be done every two
years, irrespective of the mileage" — no mileage bullet at all, purely
calendar. Spec: DOT 4, FCA MS.90039 (owner's manual). This is a firmer
source than `service_specs.BRAKE_SPEC['fluid_change_interval']`, which
remains SINGLE-SOURCE forum-only there — that module is out of this pass's
scope and was not updated to match.

### Drive (serpentine) belt — CONFIRMED interval, SINGLE-SOURCE part
Owner's manual footnote: normal duty 36,000 mi / 60,000 km max, replace
every 4 years regardless of mileage; dusty/demanding duty 18,000 mi /
30,000 km max, replace every 2 years regardless. Part: 68326261AA, one
aftermarket retailer only.

### 12V battery — CONFIRMED check interval; corrects an assumption
Owner's manual: mandatory "check battery charge status" at every one of its
10,000-mile/1-year columns. Outright replacement has no FCA-published
interval (condition/age driven). **Correction worth flagging**: this
platform was researched (independent alfaowner.com and giuliaforums.com
threads) as using a **single** 12V battery for both normal loads and the
Start/Stop system — no separate main+auxiliary pair was found documented,
contrary to the common assumption on some other manufacturers' Start/Stop
designs. Also: this vehicle's own owner's manual uses "IBS" for the
unrelated **Integrated Brake System** — not a battery sensor; don't conflate
the two. A stelvioforum thread reports MES/wiTECH have **no** explicit
"register battery replacement" function on this platform; the
charging-system monitor recalibrates itself over hours after reconnection.
Battery part: Mopar BBH8A001AA (AGM), SINGLE-SOURCE, group-size naming
inconsistent across sources (94R/H7/49/H8) — confirm physical fit, not just
a code.

### Wiper blades — CONFIRMED interval, CORROBORATED sizes
Owner's manual: "advised to replace the blades approximately once a year,"
no mileage figure. Sizes corroborated across independent fitment databases:
front 26 in (driver) / 18 in (passenger), rear 13 in. No confidently-sourced
OEM part number for the front blades this pass.

### Fuel filter — CORROBORATED (no schedule, by design)
No separate serviceable fuel filter on the US gas 2.0T: forum consensus
describes a lifetime in-tank filter sock integrated into the fuel pump
module. Corroborated by the owner's manual's own "Replace the additional
fuel filter (if equipped)" row (mandatory every 10,000 miles) — the "if
equipped" phrasing implies this filter isn't universal, and nothing found
this pass places it on the US gas 2.0T specifically.

### PCV system — UNKNOWN interval, SINGLE-SOURCE part
Not in the maintenance plan; inspect/replace on failure symptoms (oil
consumption, rough idle, crankcase-pressure DTCs). Candidate part 04893610AC
— a shared Mopar number across several Giulia/Stelvio/Jeep/Dodge products —
not independently cross-checked. Do **not** use 68324751AA (that's the 2.9L
V6/Quadrifoglio part).

### Throttle body cleaning — UNKNOWN interval
No OEM schedule found. A commonly repeated "~60,000 miles" figure could not
be traced to a specific, checkable source this pass — treated as unsourced
shop lore, not recorded as a value.

### Intake/boost hoses (inspect) — UNKNOWN interval
No OEM schedule; symptom-driven (underboost DTCs P0299/P0236, whistling,
softening boost). One aftermarket part number for a commonly-cited failure
point (turbo-to-intercooler hose, 00500536260), SINGLE-SOURCE.

### Washer fluid — CONFIRMED capacity and check interval
Owner's manual: top off every month or 600 miles (1,000 km) or before long
trips (a check, not a "change" interval). Capacity 1.1 US gal / 4.1 L, spec
CUNA NC 956-11 / MS.90043.

### A/C / cabin service — CONFIRMED interval, CORROBORATED charge weight
Owner's manual: check/maintain at an authorized dealer "at the beginning of
summer" — annual, no mileage. Refrigerant type R-1234yf is CONFIRMED
directly from the manual's fluids table, which does **not** give a charge
weight. Charge weight 535 ± 20 g comes from an industry refrigerant-quantity
reference (chassis code 949), corroborated by a second independent
aggregator's ~530 g figure — CORROBORATED at the aggregator level, not
CONFIRMED, since neither is an FCA document. Verify against the underhood
A/C label before charging. Compressor oil type/amount: not sourced.

### Power steering (EPS) — CONFIRMED: no fluid at all
Owner's manual Technical Specifications: "Rack and pinion with electric
power steering." No power-steering-fluid line appears anywhere in the
capacities/lubricants tables (unlike brake/coolant/washer fluid, which ARE
listed) — there is **no hydraulic power-steering fluid on this car**. Listed
here mainly to correct the common, incorrect assumption that it's a
serviceable fluid item.

### Hood and door lubrication — CONFIRMED interval, scope caveat
Owner's manual: "Check cleanliness of hood and luggage compartment locks,
cleanliness and lubrication of linkage," mandatory every 20,000 miles / 2
years. Note the manual's own wording is about the **hood/liftgate** lock
linkage specifically — it does **not** separately schedule door hinges. Door
hinge lubrication is good practice, not a documented FCA interval on this
car.

## Gaps (UNKNOWN)

- **Ignition coils** — no scheduled interval or part number.
- **PCV system** — no scheduled interval (part number is SINGLE-SOURCE only).
- **Throttle body cleaning** — no OEM interval at all.
- **Intake/boost hoses** — no scheduled inspection interval.
- Engine coolant drain-plug location and bleed procedure for the 2.0T engine
  circuit.
- Cabin air filter part number (three conflicting candidates, unresolved).
- Wiper blade OEM part numbers (sizes are solid; part numbers are not).
- 12V battery part number (SINGLE-SOURCE; group-size naming inconsistent
  across sources).
- A/C compressor oil type and amount.
- A/C refrigerant charge weight is CORROBORATED at aggregator level only —
  no FCA document with a charge weight was found.

All of the above: use the service manual (TechAuthority).
