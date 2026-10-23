# Routine Maintenance: Accessory Belt

How CUORE documents replacing the accessory (serpentine) belt on the reference car, a **2018 Alfa Romeo Stelvio 2.0T Q4** (VIN ZASFAKPN5J7B88115). The full procedure is in the repo at `docs/maintenance/ACCESSORY_BELT_REPLACEMENT_2.0T.md`; the structured version the maintenance page reads is the `drive_belt` item in `mes-log-mcp/mes/maintenance_specs.py`.

**This is an external reference, never a CUORE reading.** No belt, pulley or tensioner measurement from the car exists. Every figure carries a label (official, supplier, forum/workshop, or inference) and a source link, and anything not found says "not found, ask dealer / service info" ([[Evidence Model|Evidence-Model]]).

## The sourced facts

| Item | Value | Source label |
|---|---|---|
| Interval | 36,000 mi (60,000 km) and at least every 4 years; 18,000 mi (30,000 km) and every 2 years for dusty or demanding use (cold climates, town use, long idling). A visual check of belt condition and tensioning is also in the plan. | official, 2018 Stelvio owner's manual, Maintenance Plan footnote 4 |
| Belt | Mopar 68326261AA (single-source); Alfa EU 50534146; 6 ribs, 6PK1855 (1855 mm). Gates K060730, Dayco 6PK1855 and Schaeffler FB 6PK1856 are listed as equivalents. | supplier and retailer listings; single-source where marked |
| Tensioner release | A 3/8 in breaker bar in the square hole on the lower face of the tensioner, turned clockwise. No locking pin is mentioned. | workshop guide for the Giulia 2.0; Stelvio assumed the same (inference) |
| Access | Undertray (19 x T27), plastic auxiliary cover (10 mm nuts), and the turbo air intake pipe must come off. Wheel liner not mentioned. | same guide |
| Fitting | Belt goes over the idler, tensioner pulled back, belt slipped under the idler last; then turn the crank pulley clockwise by hand and check the ribs. | same guide |
| Torque values | Not found, ask dealer / service info | |
| Belt TSBs | None in `tsb_catalogue.json` (no belt, tensioner, pulley or alternator row) and none found online | |

## What the procedure covers

Scope and applicability, when (interval and symptoms), parts and tools, safety (engine cold, key away, battery disconnect not required, fingers clear of the tensioner), pre-checks with the belt off (spin each pulley, tensioner damping, alignment, grooves), step-by-step removal and fitting with a routing sketch, post-install checks (rib seating, run and listen, re-check after a short drive), what to record, and a source table with links.

## In CUORE

- The job `f3ab620b5464` (accessory belt, owner-attested plan: belt on site, install date not stated, tensioner and idlers judged fine by look and listen) carries a note pointing at the procedure. The pre-checks are where that judgement is tested once the belt is off.
- After the job, record the belt part number, odometer, date, pulley condition and who fitted it as actions on that job ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]).
- No adapter contact is part of the belt job ([[Safety Rules|Safety-Rules]]).
- If the battery is disconnected anyway, record when: it does not clear codes by itself but resets readiness, and this car is already chasing EVAP codes ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]).
